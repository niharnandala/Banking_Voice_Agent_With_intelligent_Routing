import asyncio
import sys
import sounddevice as sd
import numpy as np
import time
import subprocess
import itertools
from gnani.stt import GnaniSTTStreamClient, StreamTranscriptEvent
from connections import VACHANA_API_KEY, audio_queue

SAMPLE_RATE  = 16000  # phone calls use 16000 samples per second, studio quality not needed here
CHUNK_SIZE   = 512    # small chunk so vachana starts processing fast, big chunk causes delay on call
SILENCE_WAIT = 1.2    # lowered from 2.5 — still natural but much faster turn detection

# --- FIX: we need to know which asyncio event loop is "the" loop so the mic
# callback (which runs on PortAudio's own background thread, NOT our event loop)
# can safely hand audio back to asyncio. This gets set once start_listening() runs.
_main_loop = None

# --- FIX: while the bot is speaking, we ignore mic input so it doesn't hear
# itself and transcribe its own voice as a new user turn (echo loop bug).
_is_speaking = False


def mic_callback(indata, frames, time_info, status):
    # sounddevice fires this on a SEPARATE THREAD, not our asyncio thread.
    # asyncio.Queue.put_nowait() is NOT thread-safe, calling it directly from
    # here can corrupt the queue or randomly drop audio chunks.
    # FIX: hop back onto the main event loop thread before touching the queue.
    if _is_speaking:
        return  # drop audio while bot is talking, prevents echo/self-hearing

    if _main_loop is not None:
        _main_loop.call_soon_threadsafe(
            audio_queue.put_nowait, indata[:, 0].copy()
        )


def to_int16(audio):
    # mic gives float32, vachana wants int16
    # eg 0.5 float becomes 16383 int16, same audio different format
    return np.clip(audio * 32767, -32768, 32767).astype(np.int16)


# ---------------------------------------------------------------------------
# TEXT TO SPEECH
# ---------------------------------------------------------------------------
# FIX: only start PowerShell TTS if we're actually on Windows. Before, this
# ran unconditionally at import time, so just doing `import vachana` on
# Mac/Linux crashed immediately.
_ps_process = None

if sys.platform.startswith("win"):
    _ps_process = subprocess.Popen(
        ["powershell", "-NoExit", "-NoLogo", "-NoProfile"],
        stdin  = subprocess.PIPE,
        stdout = subprocess.PIPE,   # FIX: need stdout now so we can detect when speech finishes
        text   = True,
        bufsize = 1,                # line-buffered, so we can read output as it appears
    )
    _ps_process.stdin.write("Add-Type -AssemblyName System.Speech\n")
    _ps_process.stdin.write("$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer\n")
    _ps_process.stdin.flush()
else:
    print("WARNING: not on Windows, TTS is disabled (speak() will just print text).")

# unique marker we print after every Speak() call so we know exactly when
# PowerShell has finished talking, instead of guessing with a timer.
_DONE_MARKER_COUNTER = itertools.count()


def _speak_blocking(text):
    """
    Runs Speak() in PowerShell and BLOCKS until that specific utterance
    finishes playing, by waiting for a unique marker line on stdout.

    FIX: previously speak() just fired the command and returned instantly,
    so the code had no idea when the bot actually stopped talking. That
    caused the mic to reopen while the bot was still mid-sentence.
    """
    if _ps_process is None:
        print(f"[TTS disabled] would have said: {text}")
        return

    safe_text = text.replace('"', "'")
    marker = f"SPEECH_DONE_{next(_DONE_MARKER_COUNTER)}"

    try:
        _ps_process.stdin.write(f'$synth.Speak("{safe_text}")\n')
        _ps_process.stdin.write(f'Write-Output "{marker}"\n')
        _ps_process.stdin.flush()

        # block (this function is only ever called inside a worker thread,
        # see speak() below) until we see our marker echoed back
        while True:
            line = _ps_process.stdout.readline()
            if not line:
                break  # process died/pipe closed, stop waiting
            if marker in line:
                break
    except Exception as e:
        print(f"speak failed: {e}")


async def speak(text):
    """
    Async wrapper around _speak_blocking(). Mutes the mic for the duration
    of the speech so the bot doesn't transcribe itself, then un-mutes.

    NOTE: this is now `async def` (it used to be a plain sync function).
    Every caller in this codebase has been updated to `await speak(...)`.
    """
    global _is_speaking
    _is_speaking = True
    try:
        # _speak_blocking() blocks on a pipe read, so we run it in a thread
        # to avoid freezing the whole event loop while the bot talks.
        await asyncio.to_thread(_speak_blocking, text)
    finally:
        # FIX: drain any audio that snuck into the queue while we were
        # "muted" (mic_callback drops it, but belt-and-braces: also clear
        # anything already queued before we started speaking).
        while not audio_queue.empty():
            try:
                audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        _is_speaking = False


async def run_timer(label, stop_event):
    # shows live timer so user knows whats happening at each stage
    start = time.time()
    while not stop_event.is_set():
        elapsed = time.time() - start
        print(f"\r{label}: {elapsed:.1f}s", end="", flush=True)
        await asyncio.sleep(0.2)
    elapsed = time.time() - start
    print(f"\r{label}: {elapsed:.1f}s  done")
    return elapsed


async def start_listening(on_transcript, listen_once=False):
    # listen_once=True means stop after user speaks once and handle finishes
    # listen_once=False means keep listening forever after each reply
    global _main_loop
    _main_loop = asyncio.get_running_loop()  # FIX: remember the loop for mic_callback

    print("\nready... waiting for user to speak\n")

    done = asyncio.Event()

    while True:
        try:
            async with GnaniSTTStreamClient(
                api_key       = VACHANA_API_KEY,
                language_code = "en-IN",
                sample_rate   = SAMPLE_RATE,
            ) as stream:

                with sd.InputStream(
                    samplerate = SAMPLE_RATE,
                    blocksize  = CHUNK_SIZE,
                    dtype      = 'float32',
                    channels   = 1,
                    callback   = mic_callback
                ):
                    chunks        = []
                    silence_task  = None
                    is_processing = False

                    collecting_stop  = asyncio.Event()
                    collecting_timer = asyncio.create_task(
                        run_timer("collecting audio from mic", collecting_stop)
                    )

                    async def fire_after_silence():
                        nonlocal is_processing
                        await asyncio.sleep(SILENCE_WAIT)

                        full_text = " ".join(chunks).strip()
                        if not full_text:
                            return

                        is_processing = True

                        collecting_stop.set()
                        await collecting_timer

                        silence_stop  = asyncio.Event()
                        silence_timer = asyncio.create_task(
                            run_timer("silence detected", silence_stop)
                        )
                        silence_stop.set()
                        await silence_timer

                        vachana_stop  = asyncio.Event()
                        vachana_timer = asyncio.create_task(
                            run_timer("reading transcript", vachana_stop)
                        )
                        vachana_stop.set()
                        await vachana_timer

                        print(f"\nyou said: {full_text}\n")

                        speaking_stop  = asyncio.Event()
                        speaking_timer = asyncio.create_task(
                            run_timer("bot speaking", speaking_stop)
                        )
                        await speak("Got it, one moment.")  # FIX: now properly awaited and blocks for real duration
                        speaking_stop.set()
                        await speaking_timer

                        answer_stop  = asyncio.Event()
                        answer_timer = asyncio.create_task(
                            run_timer("getting your answer", answer_stop)
                        )

                        chunks.clear()
                        await on_transcript(full_text)

                        answer_stop.set()
                        await answer_timer

                        is_processing = False

                        if listen_once:
                            done.set()
                            return

                        print("\nready for next question\n")
                        collecting_stop.clear()
                        asyncio.create_task(
                            run_timer("collecting audio from mic", collecting_stop)
                        )

                    async def send_audio():
                        while not done.is_set():
                            try:
                                # FIX: short timeout so this loop actually wakes up
                                # and re-checks `done` instead of blocking forever
                                # on audio_queue.get() when listen_once finishes.
                                chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.5)
                            except asyncio.TimeoutError:
                                continue
                            try:
                                await stream.send_audio(to_int16(chunk).tobytes())
                            except Exception:
                                pass

                    async def receive():
                        nonlocal silence_task, is_processing
                        async for event in stream:
                            if done.is_set():
                                break
                            if isinstance(event, StreamTranscriptEvent):
                                if event.text.strip() and not is_processing:
                                    chunks.append(event.text.strip())
                                    if silence_task:
                                        silence_task.cancel()
                                    silence_task = asyncio.create_task(fire_after_silence())

                    # FIX: previously `await asyncio.gather(send_audio(), receive())`
                    # could hang forever in listen_once mode because receive() sits
                    # blocked inside `async for event in stream` with nothing to wake
                    # it up once `done` is set. Now we race both tasks against `done`
                    # being set, and explicitly cancel whichever is still running.
                    send_task    = asyncio.create_task(send_audio())
                    receive_task = asyncio.create_task(receive())
                    done_task    = asyncio.create_task(done.wait())

                    await asyncio.wait(
                        [send_task, receive_task, done_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    for t in (send_task, receive_task, done_task):
                        if not t.done():
                            t.cancel()
                    await asyncio.gather(send_task, receive_task, done_task, return_exceptions=True)

        except KeyboardInterrupt:
            print("\nstopped.")
            break
        except Exception as e:
            print(f"connection dropped: {e}, reconnecting in 1s...")
            await asyncio.sleep(1)

        if done.is_set():
            break


async def greet():
    await speak("Hello, welcome to XYZ Bank. I am your bank assistant. Ask me anything about your account.")
    print("\nready... waiting for user to speak\n")


async def listen():
    # wraps start_listening to just return text directly instead of using a callback
    result = {}

    async def capture(text):
        result["text"] = text

    await start_listening(capture, listen_once=True)
    return result.get("text", "")


if __name__ == "__main__":
    async def handle(text):
        print(f"\nprogram received: {text}\n")
        await asyncio.sleep(1)

    asyncio.run(start_listening(handle))
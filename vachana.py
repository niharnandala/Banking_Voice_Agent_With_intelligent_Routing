import asyncio
import sys
import sounddevice as sd
import numpy as np
import time
import subprocess
import itertools
from gnani.stt import GnaniSTTStreamClient, StreamTranscriptEvent
from connections import VACHANA_API_KEY, audio_queue

SAMPLE_RATE  = 16000  # i use 16000 samples per second — phone call quality, not studio
CHUNK_SIZE   = 512    # i keep chunks small so vachana starts processing fast
SILENCE_WAIT = 1.5    # i wait 1.5 seconds of silence before treating turn as done

_main_loop  = None    # i store the event loop here so mic_callback can reach it safely
_is_speaking = False  # i use this flag to mute the mic while the bot is talking

# FIX: i added this flag so the reconnect loop in start_listening knows
# when to stop retrying — before this it kept reconnecting forever after exit
_should_stop = False


def stop_listening():
    # i call this from llm_intent.py when the user says goodbye
    # it sets the flag so the reconnect loop breaks cleanly
    # instead of trying to reconnect on a shutting-down event loop
    global _should_stop
    _should_stop = True


def mic_callback(indata, frames, time_info, status):
    # sounddevice fires this on its own separate thread, not my asyncio thread
    # i cannot touch asyncio.Queue directly from here — it is not thread safe
    # so i use call_soon_threadsafe to hand the chunk to the event loop instead
    # the event loop then puts it in the queue safely on its own turn

    if _is_speaking:
        return
    # i drop all audio while the bot is speaking
    # this prevents the mic from hearing the bot's own voice
    # and transcribing it as a new user question

    if _main_loop is not None:
        _main_loop.call_soon_threadsafe(
            audio_queue.put_nowait, indata[:, 0].copy()
        )
    # i copy the audio data before putting it in the queue
    # because sounddevice reuses the same buffer for every chunk
    # without copying, the data would get overwritten before i process it


def to_int16(audio):
    # my mic gives me float32 values between -1.0 and 1.0
    # vachana wants int16 values between -32768 and 32767
    # i multiply by 32767 to scale up, clip to prevent overflow, then cast
    return np.clip(audio * 32767, -32768, 32767).astype(np.int16)


# ── TEXT TO SPEECH ─────────────────────────────────────────────────────────────

_ps_process = None
# i only start powershell if i am actually on windows
# before this fix, importing vachana on mac or linux crashed immediately

if sys.platform.startswith("win"):
    _ps_process = subprocess.Popen(
        ["powershell", "-NoExit", "-NoLogo", "-NoProfile"],
        stdin   = subprocess.PIPE,
        stdout  = subprocess.PIPE,
        text    = True,
        bufsize = 1,
    )
    # i open powershell once at startup and keep it alive
    # this avoids the 300-500ms startup cost on every speak() call
    # i need stdout piped back so i can detect when speech actually finishes

    _ps_process.stdin.write("Add-Type -AssemblyName System.Speech\n")
    _ps_process.stdin.write("$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer\n")
    _ps_process.stdin.flush()
    # i load the speech engine once here, not on every speak() call

else:
    print("WARNING: not on Windows, TTS is disabled — speak() will just print text.")

_DONE_MARKER_COUNTER = itertools.count()
# i use a counter to generate unique marker strings like SPEECH_DONE_0, SPEECH_DONE_1
# each speak() call gets its own marker so i know exactly which one finished


def _speak_blocking(text):
    # i wrote this to actually wait for speech to finish before returning
    # the old code just fired the command and returned instantly
    # so the mic would reopen while the bot was still mid-sentence
    # now i write a unique marker after the Speak() command
    # powershell processes commands in order so the marker only prints
    # after speech is fully done — i read stdout until i see the marker

    if _ps_process is None:
        print(f"[TTS disabled] would have said: {text}")
        return

    safe_text = text.replace('"', "'")
    # i replace double quotes with single quotes so powershell doesnt break
    # on sentences like: he said "hello"

    marker = f"SPEECH_DONE_{next(_DONE_MARKER_COUNTER)}"

    try:
        _ps_process.stdin.write(f'$synth.Speak("{safe_text}")\n')
        _ps_process.stdin.write(f'Write-Output "{marker}"\n')
        _ps_process.stdin.flush()

        while True:
            line = _ps_process.stdout.readline()
            if not line:
                break
            if marker in line:
                break
        # i block here reading lines until i see my marker
        # once i see it i know for sure the audio has finished playing

    except Exception as e:
        print(f"speak failed: {e}")


async def speak(text):
    # i made speak() async so the rest of my async code can await it properly
    # i set _is_speaking True first to mute the mic immediately
    # then i run _speak_blocking in a thread so it doesnt freeze the event loop
    # the event loop needs to stay running for timers and other tasks

    global _is_speaking
    _is_speaking = True
    try:
        await asyncio.to_thread(_speak_blocking, text)
    finally:
        # i drain the audio queue after speaking to remove any audio
        # that might have slipped in before the mute flag was set
        while not audio_queue.empty():
            try:
                audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        _is_speaking = False
        # i always unset the flag in finally so the mic opens again
        # even if something crashed during speech


async def run_timer(label, stop_event):
    # i use this everywhere to show live elapsed time in the terminal
    # it runs as a background task alongside the real work
    # the caller sets stop_event when the work is done
    start = time.time()
    while not stop_event.is_set():
        elapsed = time.time() - start
        print(f"\r{label}: {elapsed:.1f}s", end="", flush=True)
        await asyncio.sleep(0.2)
    elapsed = time.time() - start
    print(f"\r{label}: {elapsed:.1f}s  done")
    return elapsed


async def start_listening(on_transcript, listen_once=False):
    global _main_loop
    _main_loop = asyncio.get_running_loop()
    # i save the running loop here so mic_callback (on a different thread)
    # can use call_soon_threadsafe to hand audio back to this loop safely

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
                        # i sleep for SILENCE_WAIT seconds
                        # if a new chunk arrives before this sleep finishes
                        # receive() cancels this task and starts a fresh one
                        # so this only continues if the user was truly silent

                        full_text = " ".join(chunks).strip()
                        if not full_text:
                            return

                        is_processing = True

                        collecting_stop.set()
                        await collecting_timer

                        silence_stop  = asyncio.Event()
                        silence_timer = asyncio.create_task(run_timer("silence detected", silence_stop))
                        silence_stop.set()
                        await silence_timer

                        vachana_stop  = asyncio.Event()
                        vachana_timer = asyncio.create_task(run_timer("reading transcript", vachana_stop))
                        vachana_stop.set()
                        await vachana_timer

                        print(f"\nyou said: {full_text}\n")

                        speaking_stop  = asyncio.Event()
                        speaking_timer = asyncio.create_task(run_timer("bot speaking", speaking_stop))
                        await speak("Got it, one moment.")
                        # i await speak() so the mic stays muted until
                        # the acknowledgment is fully spoken
                        speaking_stop.set()
                        await speaking_timer

                        answer_stop  = asyncio.Event()
                        answer_timer = asyncio.create_task(run_timer("getting your answer", answer_stop))

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
                        asyncio.create_task(run_timer("collecting audio from mic", collecting_stop))

                    async def send_audio():
                        while not done.is_set():
                            try:
                                chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.5)
                                # i use a 0.5s timeout instead of blocking forever
                                # so this loop wakes up every 0.5s to check done
                                # without this it would hang after listen_once finishes
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
                                    # i cancel the old silence timer and start a fresh one
                                    # every time new text arrives — so the timer only
                                    # fires after a genuine gap in speech

                    send_task    = asyncio.create_task(send_audio())
                    receive_task = asyncio.create_task(receive())
                    done_task    = asyncio.create_task(done.wait())

                    await asyncio.wait(
                        [send_task, receive_task, done_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    # i race all three tasks — whichever finishes first wins
                    # done_task finishes when listen_once is done
                    # i then cancel whatever is still running so nothing hangs

                    for t in (send_task, receive_task, done_task):
                        if not t.done():
                            t.cancel()
                    await asyncio.gather(send_task, receive_task, done_task, return_exceptions=True)

        except KeyboardInterrupt:
            print("\nstopped.")
            break

        except Exception as e:
            if _should_stop:
                break
            # FIX: i check _should_stop before reconnecting
            # if the user said goodbye and the event loop is shutting down
            # i stop retrying instead of crashing with "cannot schedule new futures"
            print(f"connection dropped: {e}, reconnecting in 1s...")
            await asyncio.sleep(1)

        if done.is_set():
            break


async def greet():
    await speak("Hello, welcome to XYZ Bank. I am your bank assistant. Ask me anything about your account.")
    print("\nready... waiting for user to speak\n")


async def listen():
    # i wrap start_listening here to give callers a simple interface
    # instead of passing a callback they just await listen() and get text back
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
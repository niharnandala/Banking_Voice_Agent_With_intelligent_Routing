import asyncio
import sounddevice as sd
import numpy as np
import time
import pyttsx3
from gnani.stt import GnaniSTTStreamClient, StreamTranscriptEvent
from connections import VACHANA_API_KEY, audio_queue

SAMPLE_RATE  = 16000
CHUNK_SIZE   = 512
SILENCE_WAIT = 1.5

# one engine created once at start, reused for all speak calls
# pyttsx3 works fine as long as we call it from main thread only
# we are not using executor anymore bcuzz that was causing the freeze
engine = pyttsx3.init()


def mic_callback(indata, frames, time_info, status):
    # sounddevice fires this every time mic captures a chunk
    # we just put it in queue, vachana picks it up from there
    audio_queue.put_nowait(indata[:, 0].copy())


def to_int16(audio):
    # mic gives float32, vachana wants int16
    # eg 0.5 float becomes 16383 int16, same audio different format
    return np.clip(audio * 32767, -32768, 32767).astype(np.int16)


def speak(text):
    # called directly now, not from executor
    # asyncio pauses while this runs but thats fine
    # bcuzz is_processing flag already blocks new input while bot is speaking
    engine.say(text)
    engine.runAndWait()


async def run_timer(label, stop_event):
    # shows live timer in terminal so user knows whats happening at each stage
    # stops when stop_event is set from outside
    start = time.time()
    while not stop_event.is_set():
        elapsed = time.time() - start
        print(f"\r{label}: {elapsed:.1f}s", end="", flush=True)
        await asyncio.sleep(0.1)
    elapsed = time.time() - start
    print(f"\r{label}: {elapsed:.1f}s  done")
    return elapsed


async def start_listening(on_transcript):
    # bot speaks greeting first so user knows its ready
    speak("Hello, welcome to XYZ Bank. I am your bank assistant. Ask me anything about your account.")
    print("\nready... waiting for user to speak\n")

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
                    is_processing = False  # True while bot is working, ignores new audio

                    # stage 1 starts right after greeting
                    # collecting audio from mic and sending to vachana right now
                    collecting_stop  = asyncio.Event()
                    collecting_timer = asyncio.create_task(
                        run_timer("collecting audio from mic", collecting_stop)
                    )

                    async def fire_after_silence():
                        nonlocal is_processing
                        # 1.5s no new word means user stopped speaking
                        await asyncio.sleep(SILENCE_WAIT)

                        full_text = " ".join(chunks).strip()
                        if not full_text:
                            return

                        # lock processing so receive() ignores new audio from here
                        is_processing = True

                        # stage 1 done, user finished speaking
                        collecting_stop.set()
                        await collecting_timer

                        # stage 2 silence confirmed
                        silence_stop  = asyncio.Event()
                        silence_timer = asyncio.create_task(
                            run_timer("silence detected", silence_stop)
                        )
                        silence_stop.set()
                        await silence_timer

                        # stage 3 reading what vachana gave us
                        vachana_stop  = asyncio.Event()
                        vachana_timer = asyncio.create_task(
                            run_timer("reading transcript", vachana_stop)
                        )
                        vachana_stop.set()
                        await vachana_timer

                        print(f"\nyou said: {full_text}\n")

                        # stage 4 bot repeats what it heard and confirms
                        # called directly bcuzz we are already in processing mode
                        # no new audio coming in so asyncio pause is fine here
                        speaking_stop  = asyncio.Event()
                        speaking_timer = asyncio.create_task(
                            run_timer("bot speaking", speaking_stop)
                        )
                        speak(f"You said... {full_text}... I heard you, please wait.")
                        speaking_stop.set()
                        await speaking_timer

                        # stage 5 getting the answer
                        # this is where intent detection db fetch llm call all happen
                        answer_stop  = asyncio.Event()
                        answer_timer = asyncio.create_task(
                            run_timer("getting your answer", answer_stop)
                        )

                        chunks.clear()
                        await on_transcript(full_text)

                        answer_stop.set()
                        await answer_timer

                        # unlock so bot starts listening again
                        is_processing = False
                        print("\nready for next question\n")

                        # reset stage 1 for next question
                        collecting_stop.clear()
                        asyncio.create_task(
                            run_timer("collecting audio from mic", collecting_stop)
                        )

                    async def send_audio():
                        # keeps pushing mic chunks to vachana continuously
                        # runs alongside receive() so neither waits for other
                        while True:
                            chunk = await audio_queue.get()
                            try:
                                await stream.send_audio(to_int16(chunk).tobytes())
                            except Exception:
                                pass

                    async def receive():
                        nonlocal silence_task, is_processing
                        # vachana sends words one by one as user speaks
                        # we ignore everything while is_processing is True
                        # bcuzz bot is still working on previous question
                        async for event in stream:
                            if isinstance(event, StreamTranscriptEvent):
                                if event.text.strip() and not is_processing:
                                    chunks.append(event.text.strip())
                                    if silence_task:
                                        silence_task.cancel()
                                    silence_task = asyncio.create_task(fire_after_silence())

                    await asyncio.gather(send_audio(), receive())

        except KeyboardInterrupt:
            print("\nstopped.")
            break
        except Exception as e:
            print(f"connection dropped: {e}, reconnecting in 1s...")
            await asyncio.sleep(1)


if __name__ == "__main__":
    async def handle(text):
        # placeholder for now, later this calls intent detection db llm
        print(f"\nprogram received: {text}\n")
        await asyncio.sleep(1)

    asyncio.run(start_listening(handle))
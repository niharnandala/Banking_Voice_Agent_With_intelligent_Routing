import asyncio
import sounddevice as sd
import numpy as np
import time
import pyttsx3
from gnani.stt import GnaniSTTStreamClient, StreamTranscriptEvent
from connections import VACHANA_API_KEY, audio_queue

SAMPLE_RATE  = 16000  # phone calls use 16000 samples per second, studio quality not needed here
CHUNK_SIZE   = 512    # small chunk so vachana starts processing fast, big chunk causes delay on call
SILENCE_WAIT = 1.5    # 1.5s gap means user stopped speaking, sweet spot for natural conversation pace

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
    # called directly, asyncio pauses while this runs
    # thats fine bcuzz is_processing blocks new input while bot is speaking
    engine.say(text)
    engine.runAndWait()


async def run_timer(label, stop_event):
    # shows live timer so user knows whats happening at each stage
    start = time.time()
    while not stop_event.is_set():
        elapsed = time.time() - start
        print(f"\r{label}: {elapsed:.1f}s", end="", flush=True)
        await asyncio.sleep(0.1)
    elapsed = time.time() - start
    print(f"\r{label}: {elapsed:.1f}s  done")
    return elapsed


async def start_listening(on_transcript, listen_once=False):
    # listen_once=True means stop after user speaks once and handle finishes
    # listen_once=False means keep listening forever after each reply
    speak("Hello, welcome to XYZ Bank. I am your bank assistant. Ask me anything about your account.")
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
                        speak(f"You said... {full_text}... I heard you, please wait.")
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
                        while True:
                            if done.is_set():
                                break
                            chunk = await audio_queue.get()
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

                    await asyncio.gather(send_audio(), receive())

        except KeyboardInterrupt:
            print("\nstopped.")
            break
        except Exception as e:
            print(f"connection dropped: {e}, reconnecting in 1s...")
            await asyncio.sleep(1)

        if done.is_set():
            break


if __name__ == "__main__":
    async def handle(text):
        print(f"\nprogram received: {text}\n")
        await asyncio.sleep(1)

    asyncio.run(start_listening(handle))
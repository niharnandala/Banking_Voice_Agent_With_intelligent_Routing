import os
import asyncio
import sounddevice as sd
import numpy as np
import time
import psycopg2
from groq import Groq
from gnani.stt import GnaniSTTStreamClient, StreamTranscriptEvent
from dotenv import load_dotenv
load_dotenv()



# groq is the llm we are using to find what customer is asking
# free and fast so picked this over openai
# eg: "what is my balance" → groq says "personal"
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))


# one db connection at start, reused for whole call
# faster than opening new connection for every question customer asks
# eg: customer gives id CU001 → we get ravi's balance emi loan from here
db_conn = psycopg2.connect(
    host     = "localhost",
    database = "bankbot",
    user     = os.environ.get("DB_USER"),
    password = os.environ.get("DB_PASSWORD"),
    port     = "5432"
)


# vachana converts speech to text and text back to speech
# whisper fails on hinglish and noisy phone audio, vachana is trained on exactly that
# eg: "mera balance kya hai" on noisy call → vachana gets it right
VACHANA_API_KEY = os.environ.get("VACHANA_API_KEY")
SAMPLE_RATE = 16000  # phone call standard, 16000 samples per second
CHUNK_SIZE  = 512    # small chunk so vachana starts processing fast, big chunk causes delay on call


# mic puts captured audio here, vachana picks from here
# both work without waiting for each other bcuzz of this queue in between
audio_queue = asyncio.Queue()


# sounddevice fires this every time mic captures one chunk, we just put it in queue
def mic_callback(indata, frames, time_info, status):
    audio_queue.put_nowait(indata[:, 0].copy())


# mic gives float32, vachana wants int16, this converts it
# eg: 0.5 float → 16383 int16, same audio different format
def to_int16(audio):
    return np.clip(audio * 32767, -32768, 32767).astype(np.int16)


# keeps mic open and listening until ctrl+c
# if vachana drops connection it waits 1 second and reconnects instead of crashing
async def start_listening():
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
                    print("listening... speak now\n")
                    t_start = None

                    # send_audio keeps pushing mic audio to vachana
                    # receive keeps pulling transcript back from vachana
                    # asyncio.gather runs both together so neither waits for other
                    async def send_audio():
                        nonlocal t_start
                        while True:
                            chunk = await audio_queue.get()
                            if t_start is None:
                                t_start = time.time()
                            try:
                                await stream.send_audio(to_int16(chunk).tobytes())
                            except Exception:
                                pass

                    async def receive():
                        nonlocal t_start
                        async for event in stream:
                            if isinstance(event, StreamTranscriptEvent):
                                if event.text.strip():
                                    total = round(time.time() - t_start, 2) if t_start else 0
                                    print(f"> {event.text}")
                                    # logging this to measure full pipeline speed later
                                    # above 4 seconds on a call and customer feels the wait
                                    print(f"  latency: {event.latency}ms | total: {total}s\n")
                                    t_start = None

                    await asyncio.gather(send_audio(), receive())

        except KeyboardInterrupt:
            print("\nstopped.")
            break
        except Exception as e:
            print(f"connection dropped: {e}, reconnecting in 1s...")
            await asyncio.sleep(1)
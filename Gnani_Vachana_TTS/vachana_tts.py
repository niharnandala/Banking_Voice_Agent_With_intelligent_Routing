import sys
import os
import time
import io
import wave
import asyncio
import numpy as np
from gnani.tts import GnaniTTSRealtimeClient, AudioConfig

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# i add the project root to Python's path
# this file sits inside vachana_stt/ so without this
# Python cant find the connections/ folder at the project root

from connections.connections import VACHANA_API_KEY, VACHANA_TTS
# same key works for both STT and TTS, confirmed with Vachana

# i do NOT import sounddevice at the top of this file
# sounddevice needs portaudio and a real audio device to exist
# app.py imports this file and app.py runs on a server with no audio hardware
# importing sounddevice at the top would crash the server on startup
# i only import it inside _play_audio() which only ever runs on my local machine


VOICE = "Riya"
# i chose Riya Female voice
# fits a banking assistant naturally
# other options are Pranav Male, Kaveri Female, Shubhra Female, Deepak Male

SAMPLE_RATE = 44100
# i use 44100 for full quality audio
# Vachana sends at this rate so matching it prevents pitch or speed distortion

NUM_CHANNELS = 1
# i use mono because phone calls are always mono
# stereo doubles data size for no benefit in a voice assistant

SAMPLE_WIDTH = 2
# 2 bytes means 16 bit audio which is standard quality for voice
# gives good quality without being unnecessarily large


async def get_audio(text):
    # i call Vachana TTS and return one clean WAV file as bytes
    # the /speak endpoint in app.py calls this and streams bytes to the browser
    # browser receives a single proper WAV file and plays it natively

    # i ask Vachana for raw PCM with no headers per chunk
    # then i wrap everything in ONE proper WAV header at the very end
    # previously i asked for container=wav which put a header on every chunk
    # gluing those chunks together gave the browser multiple headers in one file
    # browser refused to play it so i switched to raw and build the header myself

    tts_start = time.time()

    try:
        async with GnaniTTSRealtimeClient(api_key=VACHANA_TTS) as client:
            all_audio = b""
            first_chunk = True
            chunk_count = 0

            async for chunk in client.synthesize(
                text,
                voice=VOICE,
                audio_config=AudioConfig(
                    sample_rate=SAMPLE_RATE,
                    num_channels=NUM_CHANNELS,
                    sample_width=SAMPLE_WIDTH,
                    encoding="linear_pcm",
                    container="raw"
                    # raw means pure PCM bytes with zero headers per chunk
                    # i build the single correct WAV header myself below
                )
            ):
                if first_chunk:
                    print(f"[timing] first TTS chunk arrived: {time.time() - tts_start:.2f}s")
                    # i log when the first chunk arrives
                    # this is the real latency the user feels before audio starts
                    # target is under 500ms from calling get_audio to first chunk
                    first_chunk = False

                all_audio += chunk
                chunk_count += 1

            if not all_audio:
                raise RuntimeError("Vachana TTS returned zero bytes")
            # i moved this check up here, before any of the timing math below
            # audio_duration depends on len(all_audio), and the real time factor
            # divides by audio_duration, so if all_audio ever came back empty
            # that division would blow up with a ZeroDivisionError before this
            # RuntimeError ever got a chance to fire, which just meant i saw a
            # confusing crash instead of the clear message i actually wrote

            total_tts_time = time.time() - tts_start
            audio_duration = len(all_audio) / 2 / SAMPLE_RATE
            # i divide by 2 because sample width is 2 bytes per sample
            # this gives the actual duration of the synthesised audio in seconds

            print(f"[timing] TTS total time: {total_tts_time:.2f}s")
            print(f"[timing] audio duration: {audio_duration:.2f}s")
            print(f"[timing] chunks received: {chunk_count}")
            print(f"[timing] real time factor: {total_tts_time / audio_duration:.2f}x")
            # real time factor tells me how fast TTS is relative to audio length
            # if audio is 3s long and TTS took 1.5s then RTF is 0.5x
            # anything below 1.0x means TTS is faster than real time which is good
            # above 1.0x means TTS is slower than speaking which is a problem

            # i build one clean WAV file from all the raw PCM bytes
            # wave.open with io.BytesIO writes to memory not to disk
            # i set the same format params i used when asking Vachana for audio
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(NUM_CHANNELS)
                wav_file.setsampwidth(SAMPLE_WIDTH)
                wav_file.setframerate(SAMPLE_RATE)
                wav_file.writeframes(all_audio)
                # one header at the front, all audio data after it
                # this is exactly what the browser's Audio element expects

            return wav_buffer.getvalue()

    except Exception as e:
        print(f"[error] get_audio failed: {e}")
        raise
        # i re raise so app.py's /speak endpoint knows it failed
        # and returns a proper 500 to the browser instead of silent empty audio


async def stream_audio(text):
    # i yield raw PCM chunks directly as they arrive from Vachana
    # FastAPI StreamingResponse sends each chunk to the browser immediately
    # browser receives chunks and plays them using Web Audio API in real time
    # user hears audio almost immediately instead of waiting for full synthesis
    # this is the low latency path used by the streaming /speak endpoint

    tts_start = time.time()
    first_chunk = True
    chunk_count = 0
    total_bytes = 0

    try:
        buffer_audio = b""
        BUFFER_THRESHOLD = 13230  # about 150ms of audio at 44100Hz, 16 bit mono
        async with GnaniTTSRealtimeClient(api_key=VACHANA_TTS) as client:
            async for chunk in client.synthesize(
                text,
                voice=VOICE,
                audio_config=AudioConfig(
                    sample_rate=SAMPLE_RATE,
                    num_channels=NUM_CHANNELS,
                    sample_width=SAMPLE_WIDTH,
                    encoding="linear_pcm",
                    container="raw"
                    # raw PCM chunks with no headers
                    # browser Web Audio API handles raw int16 PCM directly
                    # no WAV header needed because we are not building a file
                )
            ):
                if first_chunk:
                    print(f"[timing] stream first chunk: {time.time() - tts_start:.2f}s")
                    # i log when the very first chunk arrives
                    # this is what determines how quickly the user hears something
                    first_chunk = False

                chunk_count += 1
                total_bytes += len(chunk)
                buffer_audio += chunk
                if len(buffer_audio) >= BUFFER_THRESHOLD:
                    yield buffer_audio
                    buffer_audio = b""
            if buffer_audio:
                yield buffer_audio
            # stream's done but some audio never hit the 150ms threshold
            # flush it anyway so the last bit of the sentence doesn't get dropped

        if total_bytes == 0:
            print("[timing] stream produced zero bytes, skipping RTF calculation")
            # same idea as get_audio, i check for zero bytes before dividing
            # so a silent or empty response never causes a ZeroDivisionError here
        else:
            total_time = time.time() - tts_start
            audio_duration = total_bytes / 2 / SAMPLE_RATE

            print(f"[timing] stream total time: {total_time:.2f}s")
            print(f"[timing] stream audio duration: {audio_duration:.2f}s")
            print(f"[timing] stream chunks sent: {chunk_count}")
            print(f"[timing] stream real time factor: {total_time / audio_duration:.2f}x")

    except Exception as e:
        print(f"[error] stream_audio failed: {e}")
        raise
        # fixed: this used to just print and then let the generator end
        # silently, with no re-raise. that meant a mid-stream TTS failure
        # produced a truncated/empty audio stream with zero indication
        # anywhere up the call stack that something went wrong — app.py's
        # /speak endpoint wraps this in its own try/except that could only
        # ever catch something if this actually raised
        # re-raising here lets that outer handler in app.py log it too, so
        # the failure is visible at both layers instead of disappearing
        # after this one print statement
        # note: this doesn't change what the browser experiences — the HTTP
        # response has already started streaming with a 200 status by the
        # time any mid-stream error can happen, so there's no way to turn
        # this into a proper error status for the client at this point,
        # the stream just still ends early either way. this fix is about
        # server-side visibility, not client-side behavior


async def speak(text):
    # i use this for playing audio locally through the speaker
    # voice_client.py calls this on the local machine
    # completely separate from get_audio and stream_audio which are for the browser
    speak_start = time.time()

    try:
        async with GnaniTTSRealtimeClient(api_key=VACHANA_API_KEY) as client:
            all_audio = b""

            async for chunk in client.synthesize(
                text,
                voice=VOICE,
                audio_config=AudioConfig(
                    sample_rate=SAMPLE_RATE,
                    num_channels=NUM_CHANNELS,
                    sample_width=SAMPLE_WIDTH,
                    encoding="linear_pcm",
                    container="raw"
                    # raw works fine here because sounddevice plays raw PCM directly
                    # no header needed for local playback through sounddevice
                )
            ):
                all_audio += chunk

            if all_audio:
                audio_duration = len(all_audio) / 2 / SAMPLE_RATE
                print(f"[timing] local speak synthesis: {time.time() - speak_start:.2f}s")
                print(f"[timing] local audio duration: {audio_duration:.2f}s")
                _play_audio(all_audio)

    except Exception as e:
        print(f"[error] speak() failed: {e}")


def _play_audio(raw_bytes):
    import sounddevice as sd
    # i import sounddevice here, not at the top of the file
    # this function only ever runs from voice_client.py on my local machine
    # app.py never calls this so sounddevice never loads on the server
    # putting it at the top would crash FastAPI on any server without audio hardware

    audio_array = np.frombuffer(raw_bytes, dtype=np.int16)
    play_start = time.time()

    sd.play(audio_array, samplerate=SAMPLE_RATE)
    sd.wait()
    # sd.wait() blocks until playback is fully done
    # without this the next operation starts while audio is still playing

    print(f"[timing] local playback duration: {time.time() - play_start:.2f}s")

    time.sleep(0.5)
    # i add 500ms after sd.wait() because the hardware buffer
    # takes a moment to fully flush after sd.wait() returns
    # without this the last word gets slightly cut off


if __name__ == "__main__":
    async def test():
        print("testing Vachana TTS...")
        await speak("Hello, welcome to XYZ Bank. How can I help you today?")
        print("done")

    asyncio.run(test())
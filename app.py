import os
import uuid
import asyncio
import time
import io
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
from llm_intent import run_intent
from Gnani_Vachana_TTS.vachana_tts import get_audio, stream_audio
# i import both get_audio and stream_audio from vachana_tts
# get_audio returns a complete WAV file as bytes for simple playback
# stream_audio yields raw PCM chunks for low latency streaming playback
# both exist because different situations need different approaches


async def cleanup_dead_sessions():
    # i run this forever in the background every 5 minutes
    # it finds sessions idle for more than 10 minutes and removes them
    # without this users who just close the tab leave dead sessions in memory
    # over hundreds of calls this becomes a real memory leak
    while True:
        await asyncio.sleep(300)
        now  = time.time()
        dead = [
            sid for sid, data in sessions.items()
            if now - data.get("last_active", now) > 600
        ]
        for sid in dead:
            del sessions[sid]
            print(f"[cleanup] dead session removed: {sid}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(cleanup_dead_sessions())
    # i start the cleanup task inside lifespan
    # this is the correct modern FastAPI way — on_event startup is deprecated
    # the task runs in the background for the whole app lifetime

    try:
        _warmup_start = time.time()
        import handlers.general  # noqa: F401
        # handlers.general is normally imported lazily inside llm_intent.py,
        # the first time a real question actually gets classified as
        # "general" — and that first import is also the first time
        # scripts/knowledge_base.py loads its embedding model into memory,
        # which can take several seconds on its own.
        # that meant the very first live "general" question of the server's
        # whole life paid that cold-start cost in front of an actual
        # customer, stacked on top of the normal LLM call — exactly the
        # kind of pause that makes someone think the bot has frozen.
        # importing it here during startup pays that cost once, before
        # anyone is on the line, so every real request after that is just
        # the normal knowledge-base search + LLM call, nothing extra.
        print(f"[startup] handlers.general warmed up in {time.time() - _warmup_start:.2f}s")
    except Exception as e:
        # same defensive pattern as connections.py's DB connect at import
        # time: if warmup fails (bad path, missing index, etc) we log it
        # and keep the server running instead of crashing on startup —
        # general.py's own try/except around search_knowledge_base already
        # handles a broken knowledge base gracefully per-request, so a
        # failed warmup just means the first real request pays the cold
        # start after all, not that the whole app goes down
        print(f"[warning] handlers.general warmup failed: {e}")

    yield


app = FastAPI(lifespan=lifespan)
# app must be created before any @app.route decorators below
# Python runs top to bottom — decorating before app exists is a NameError

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # i allow all origins so the frontend can talk to this API from any URL
    # in production tighten this to only your actual domain
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions = {}
# i store each caller's conversation here
# key is session_id, value is history, state, and last_active time
# two callers never share history or state with each other

APP_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.html")
# fixed: /ui used to do FileResponse("app.html"), a path relative to the
# process's current working directory, NOT to where app.py itself lives
# if uvicorn is ever started from a different folder than the one containing
# app.html, that would 404/500 instead of serving the page
# building the path off __file__ makes it work no matter where the server
# is launched from


def new_conversation():
    # i create a fresh conversation for every new caller
    # history seeds with the opening greeting so LLM always has context
    # state tracks routing, retries, and smalltalk escalation
    # last_active is checked by cleanup to find idle sessions
    return {
        "history": [{
            "role"    : "assistant",
            "content" : "Hello, welcome to XYZ Bank. I am your bank assistant. Ask me anything about your account."
        }],
        "state": {
            "handler"         : None,
            "waiting_for"     : None,
            "retry_count"     : 0,
            "smalltalk_count" : 0
        },
        "last_active": time.time()
    }


class ChatRequest(BaseModel):
    session_id : str
    text       : str
# pydantic validates automatically
# missing fields return a 422 error without me writing any validation code


class SpeakRequest(BaseModel):
    text: str
# separate model for the speak endpoints
# only needs text, no session id required


@app.get("/")
def home():
    return {"message": "Banking Voice Agent is running"}


@app.get("/health")
def health_check():
    # purely a read-only status check for the frontend's small "connected to
    # Neon" dot — doesn't touch sessions, chat, or anything else. checking
    # "db_conn is not None" alone wouldn't be enough here: that only tells us
    # the connection succeeded once, back at server startup. a long-lived
    # connection can silently drop later (Neon can recycle idle connections,
    # network blips happen), so this actually runs a trivial query every time
    # it's called to confirm the connection is still alive right now
    from connections.connections import db_conn

    db_ok = False
    if db_conn is not None:
        conn = db_conn.getconn()

        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            db_ok = True
        except Exception as e:
            print(f"[health] db check failed: {e}")
            db_ok = False
        finally:
            db_conn.putconn(conn)

    return {"db_connected": db_ok}


@app.get("/ui")
def serve_ui():
    # i serve the HTML through FastAPI so the page loads from http://
    # browser blocks audio autoplay and cross-origin API calls from file:// URLs
    # serving through FastAPI fixes both problems at once
    return FileResponse(APP_HTML_PATH)


@app.post("/session")
def create_session():
    # app calls this first when a new call starts
    # i create a fresh conversation and store it under a unique session id
    # the app sends this session_id with every /chat request after this
    session_id = str(uuid.uuid4())
    sessions[session_id] = new_conversation()
    print(f"\n[session] created: {session_id}\n")
    return {"session_id": session_id}


@app.post("/chat")
async def chat(request: ChatRequest):
    if request.session_id not in sessions:
        # session doesnt exist — either expired or never created
        return {"error": "session not found, please call /session first"}

    conversation = sessions[request.session_id]
    conversation["last_active"] = time.time()
    # i update last_active on every message
    # so active sessions never accidentally get cleaned up

    start    = time.time()
    response = await run_intent(conversation, request.text)

    total_time = time.time() - start
    print(f"[timing] chat response time: {total_time:.2f}s")
    # i log every request time so i can spot slow responses immediately
    # target is under 2.5 seconds total
    # if consistently above that i need to investigate which LLM call is slow

    metrics = {
        "total_ms" : round(total_time * 1000),
        "stages"   : conversation.pop("timings", []),
        "intent"   : conversation.get("last_intent")
    }
    # additive only — this is exactly the same numbers that already get
    # printed to the server console above and inside llm_intent.py /
    # personal.py / general.py, just handed back to the frontend so a
    # metrics panel can display them without anyone needing to tail the
    # terminal. .pop() clears "timings" off the conversation so next
    # turn's stages don't pile up on top of this turn's

    if response == {"response": "exit"}:
        del sessions[request.session_id]
        print(f"[session] ended and cleaned up: {request.session_id}\n")
        return {
            "response" : "Thank you for calling XYZ Bank. Have a great day. Goodbye.",
            "ended"    : True,
            "metrics"  : metrics
        }

    return {
        "response" : response.get("response", "") if isinstance(response, dict) else response,
        "ended"    : False,
        "metrics"  : metrics
    }


@app.post("/speak")
async def speak_endpoint(request: SpeakRequest):
    # browser sends text here, i stream raw PCM chunks back immediately
    # browser receives chunks and plays them using Web Audio API as they arrive
    # user hears audio almost immediately — no waiting for full synthesis
    # this is the low latency streaming path
    start = time.time()
    print(f"[timing] /speak called for {len(request.text)} chars")

    async def generate():
        try:
            async for chunk in stream_audio(request.text):
                yield chunk
        except Exception as e:
            print(f"[error] /speak stream failed: {e}")
            # stream_audio now re-raises after logging instead of silently
            # swallowing errors, so this except block actually has something
            # to catch here now — previously stream_audio's own try/except
            # ate the exception internally and this outer one never fired
            # note: by the time an error happens mid-stream, the 200 response
            # and headers are already sent to the browser, so there's no way
            # to turn this into an HTTP error status at this point — the
            # stream just ends early. this at least makes the failure visible
            # in the server logs at both layers instead of only one

    response = StreamingResponse(
        generate(),
        media_type = "application/octet-stream"
        # i use octet-stream not audio/wav because these are raw PCM chunks
        # not a complete WAV file — browser Web Audio API handles raw bytes directly
    )

    print(f"[timing] /speak streaming started: {time.time() - start:.2f}s")
    return response
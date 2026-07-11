# Banking Voice Agent with Intelligent Routing

A production-grade voice agent for Indian banking that listens, understands, and responds in English, Hindi, Telugu, Hinglish, and Tenglish. No menus. No buttons. Just a conversation.

---

## Layer 1 — What it does

A customer calls. They speak naturally in whatever language they are comfortable in. The agent understands what they want, verifies who they are, fetches their real account data, and speaks back a natural response — all in under 4 seconds per turn.

```
customer speaks          →    agent understands    →    agent responds
"mera balance kya hai"        personal query             "Aapka balance
"i want to know my EMI"       personal query              1.5 lakh rupees hai sir"
"how to open account"         general query              pulls from knowledge base
"address change karna hai"    escalation                 raises staff ticket
```

Real numbers from a live session:

```
intent classification     0.0s
customer id extraction    0.0s
knowledge base search     0.0s
answer generation         0.0s
bot speaking              2.8s to 3.4s
total turn time           under 4 seconds
```

---

## Layer 2 — How it works

Five things happen on every call, in this order every time.

```
LISTEN
the mic opens, audio streams to Vachana STT in real time
1.5 seconds of silence means the customer is done talking

UNDERSTAND
the full transcript goes to an LLM intent classifier
five possible intents: personal, general, escalate, smalltalk, exit
works in English, Hindi, Telugu, and any mix of the three

ROUTE
personal   →   verify customer id, fetch account data, answer
general    →   search knowledge base, retrieve relevant chunks, answer
escalate   →   raise a ticket, hand off to staff
smalltalk  →   reset conversation, reintroduce the bot
exit       →   say goodbye, end call cleanly

FETCH
personal queries hit the customer database
general queries hit a ChromaDB vector store with bank policy documents
nothing is made up — every answer comes from real data

RESPOND
LLM generates a natural spoken response
cleaned of any markdown before speaking
spoken out loud via TTS, mic reopens only after bot finishes
```

---

## Layer 3 — Why these tools and these decisions

Every tool in this stack was chosen for a reason.

**Vachana STT by Gnani.ai over Whisper or Azure**

Indian callers do not speak textbook English. They say "see you zero zero one" for CU001, "mera balance kya hai" mid-conversation, and switch languages every sentence. Vachana is trained on over a million hours of real Indian voice data across BFSI specifically. Generic models fail on this. Vachana does not.

**Groq with LLaMA 3.1 8B Instant over OpenAI**

Speed is everything on a voice call. Groq's inference is sub-100ms for classification tasks. OpenAI at the same model size is 3 to 5x slower. For a system where every second of silence feels wrong to a caller, this matters.

**ChromaDB with Dynamic Drop Detection over fixed similarity threshold**

Standard RAG uses a fixed threshold like 0.7 to decide which chunks are relevant. This breaks across different models and datasets — for one model 0.65 is excellent, for another 0.82 is average. This system looks at the shape of scores instead.

```
scores:   0.91   0.89   0.85   0.61   0.58
gaps:            0.02   0.04   0.24   0.03

gap of 0.24 between position 2 and 3 is bigger than threshold 0.15
cut here — keep first 3, discard the rest
```

This adapts to whatever the model produces. No manual tuning needed when the knowledge base changes.

**all-MiniLM-L6-v2 for embeddings**

384 dimensions, fast inference, good enough accuracy for FAQ-style banking queries. Loads once at startup, stays in memory for the entire session. Never reloads mid-call.

**PowerShell System.Speech with marker-based completion**

The original approach fired a Speak command and returned instantly. The mic would reopen while the bot was still talking, capturing the bot's own voice as a new user question — a self-hearing loop. The fix: after every Speak command, a unique marker is written to stdout. The code blocks reading stdout until that marker appears. Speech is guaranteed done before the mic opens.

```
old way    fire Speak()  →  return immediately  →  mic opens  →  bot hears itself
new way    fire Speak()  →  write marker        →  read stdout until marker seen  →  mic opens
```

---

## Layer 4 — Architecture and file structure

```
llm_intent.py                 entry point, main loop, intent router
vachana_stt/
    vachana.py                mic input, STT streaming, TTS output, silence detection
handlers/
    personal.py               customer id extraction, DB lookup, account answers
    general.py                knowledge base search, policy answers
    escalate.py               ticket generation, staff handoff
    smalltalk.py              conversation reset, bot reintroduction
scripts/
    queries.py                database functions, customer data fetch, id validation
knowledge_base.py             ChromaDB search, embedding, dynamic drop detection
utils/
    utils.py                  shared helpers: JSON parser, markdown cleaner
connections/
    connections.py            API keys, DB connection, audio queue
```

**The flow in code terms:**

```
asyncio.run(main())
    │
    ├── await greet()                          bot speaks welcome
    │
    └── while True:
            │
            ├── text = await listen()          mic opens, STT streams, silence closes
            │
            ├── await run_intent(text)
            │       │
            │       ├── personal  → handle_personal()
            │       │       ├── await listen()          ask for customer id
            │       │       ├── LLM extracts id
            │       │       ├── validate_customer_id()  check DB
            │       │       ├── get_customer_full_data() fetch everything
            │       │       └── LLM answers from data
            │       │
            │       ├── general   → handle_general()
            │       │       ├── search_knowledge_base()  vector search
            │       │       ├── dynamic drop detection   filter chunks
            │       │       └── LLM answers from chunks
            │       │
            │       ├── escalate  → handle_escalate()
            │       │       └── raise ticket, return exit
            │       │
            │       ├── smalltalk → handle_smalltalk()
            │       │       └── clear history, reintroduce bot
            │       │
            │       └── exit      → speak goodbye, return exit
            │
            └── if result == "exit": break
```

---

## Layer 5 — The bugs that were fixed and why they mattered

**Thread safety on the audio queue**

sounddevice fires mic_callback on its own OS thread. asyncio.Queue is not thread safe. Calling put_nowait directly from that thread while the event loop is doing a get on the same queue causes race conditions on internal data structures — silent audio drops, occasional crashes, never reproducible consistently. Fix: call_soon_threadsafe hands the chunk to the event loop which puts it in the queue safely on its own turn.

```python
# wrong — audio thread touches queue directly
audio_queue.put_nowait(indata[:, 0].copy())

# correct — audio thread asks event loop to do it
_main_loop.call_soon_threadsafe(audio_queue.put_nowait, indata[:, 0].copy())
```

**TTS completion sync**

Old code fired Speak and returned instantly. Mic reopened mid-sentence. Bot transcribed its own voice as new user input. Fix: unique marker written after each Speak, stdout read until marker appears, only then mic opens.

**Infinite recursion between personal and intent classifier**

When a user cannot provide a valid customer id, personal.py calls back into run_intent which calls back into handle_personal. Without a counter this loops forever. Fix: retry_count passed through every call, escalates to human after 3 failures.

**listen_once hang**

In listen_once mode, receive() sits blocked inside async for event in stream with nothing to wake it up once done is set. The whole listening session would hang. Fix: send_audio, receive, and done.wait run as separate tasks raced with asyncio.wait FIRST_COMPLETED, then explicitly cancelled.

**Circular imports**

llm_intent.py imports smalltalk.py. smalltalk.py needs run_intent from llm_intent.py. Top level import causes Python to get stuck — A imports B, B imports A, A is still loading. Fix: import run_intent inside the function body, not at module level. Same pattern in personal.py.

**LLM JSON parsing**

LLMs told to return only JSON sometimes wrap it in markdown fences or add a sentence. Raw json.loads crashes on this. Fix: strip backtick fences, strip json label, try parse, fall back to safe default on failure. Used everywhere LLM output is parsed.

**20 second silence timeout**

If nobody speaks, the program waits forever. silence_since tracks last audio chunk time inside send_audio. Every 0.5s timeout check compares against 20 seconds. If exceeded, bot speaks goodbye and sets done to shut everything down cleanly.

---

## How to run it

**Requirements**

```
Python 3.10 or above
MySQL database with customers, accounts, loans tables
Vachana API key from Gnani.ai
Groq API key
Windows (TTS uses PowerShell System.Speech)
```

**Install dependencies**

```
pip install sounddevice numpy groq chromadb sentence-transformers mysql-connector-python
pip install gnani-stt
```

**Set up environment**

Create a connections/connections.py file:

```python
import asyncio
import groq
import mysql.connector

VACHANA_API_KEY = "your_vachana_key"
audio_queue     = asyncio.Queue()
groq_client     = groq.Groq(api_key="your_groq_key")
db_conn         = mysql.connector.connect(
    host     = "localhost",
    user     = "your_user",
    password = "your_password",
    database = "your_db"
)
```

**Build the knowledge base**

```
python knowledge_base.py
```

Run this once. ChromaDB saves to disk. Never needs to run again unless bank_policies.jsonl changes.

**Start the agent**

```
python llm_intent.py
```

---

## What a real session looks like

```
bot:   Hello, welcome to XYZ Bank. I am your bank assistant.

user:  mera balance kya hai
bot:   Let me check that for you.
       intent: personal, confidence: 0.95
bot:   Please tell me your customer id.

user:  my customer id is cu 007
       customer_id: CU007
bot:   Dhanyawad sir. Aapka balance 1.5 lakh rupees hai.
       Is there anything else I can assist you with today sir?

user:  could you get me some bank emi policies
bot:   Let me look that up for you.
       intent: general, confidence: 0.80
       kept 5 chunks after drop detection
bot:   EMI har mahine 5 ko automatically deducted hota hai.
       Bounce charge 500 rupees per instance hai sir.

user:  i want to change my bank account
bot:   Let me check that for you.
       intent: escalate, confidence: 0.85
       ESCALATION TICKET RAISED
       ticket id: 43A5E499
bot:   I have raised a ticket for you sir.
       A staff member will contact you shortly.
```

---

Built by Nihar Nandala
github.com/niharnandala/Banking_Voice_Agent_With_intelligent_Routing
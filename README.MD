<div align="center">

# Banking Voice Agent

A voice bot that lets a bank customer talk normally, in whatever language they actually speak, and get a real answer back about their account.

Built by Nihar Nandala

[![Python](https://img.shields.io/badge/Python-3.10+-3b82f6?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/Routing-LangGraph_state_machine-8b5cf6?style=flat-square)](https://langchain-ai.github.io/langgraph/)
[![Groq](https://img.shields.io/badge/LLM-Groq_gpt--oss--120b-f59e0b?style=flat-square)](https://groq.com)
[![Vachana](https://img.shields.io/badge/TTS-Vachana_by_Gnani-10b981?style=flat-square)](https://vachana.ai)
[![Postgres](https://img.shields.io/badge/DB-Postgres_(Neon)-336791?style=flat-square&logo=postgresql&logoColor=white)](https://neon.tech)
[![License](https://img.shields.io/badge/License-MIT-muted?style=flat-square)](LICENSE)

[![Live Demo](https://img.shields.io/badge/▶_TRY_THE_LIVE_DEMO-22c55e?style=for-the-badge)](https://banking-voice-agent-with-intelligent.onrender.com/ui)

**[full build notes, bugs and all →](ENGINEERING.md)**

https://github.com/user-attachments/assets/235f395f-43f0-465a-a93a-697416c0d638

</div>

---

### contents

- [what it does](#what-it-does)
- [how it routes a request](#how-it-routes-a-request)
- [the part that isn't a single turn](#the-part-that-isnt-a-single-turn)
- [screenshots](#screenshots)
- [what i actually measured, not just claimed](#what-i-actually-measured-not-just-claimed)
- [where the latency actually goes](#where-the-latency-actually-goes)
- [where it fails, and what the failures mean](#where-it-fails-and-what-the-failures-mean)
- [what i picked and why](#what-i-picked-and-why)
- [the honest parts](#the-honest-parts)
- [run it yourself](#run-it-yourself)
- [file layout](#file-layout)

---

## what it does

```
"mera balance kya hai"          →  personal    →  db lookup       →  hindi reply
"how to open an account"        →  general     →  rag search      →  policy answer
"address change karna hai"      →  escalate    →  ticket raised   →  human takes over
```

people don't talk to a bank in clean textbook english, they mix hindi and english mid sentence, type hindi using english letters, switch languages between turns. this is built around that instead of pretending it doesn't happen.

try it yourself, seeded fake customers, nothing real: `CU001` `CU002` `CU003` `CU004` `CU005` `CU007`

`CU004` is the interesting one. balance below the minimum **and** an overdue emi, so you can watch it answer two bad-news questions in a row without contradicting itself.

first request after it's been idle can take 30 to 60 seconds, that's render waking the container back up, not the app being broken.

---

## how it routes a request

every message gets sorted into one of five buckets before anything else happens. each bucket has completely different machinery behind it, which is the whole point, a policy question and an account question are not the same problem and shouldn't share a code path.

```mermaid
flowchart TD
    A[user speaks] --> B{already waiting<br/>on an answer?}
    B -->|yes| P[personal handler<br/>classifier skipped]
    B -->|no| C[classify_intent via Groq<br/>returns intent + confidence + language]
    C --> D{confidence >= 0.7?}
    D -->|no| U[ask them to rephrase]
    D -->|yes| E{which intent}
    E -->|personal| P
    E -->|general| G[vector search over policy] --> G2[answer from retrieved chunks only]
    E -->|escalate| I[raise ticket] --> J[human takes over]
    E -->|smalltalk| K[reset and re-greet]
    E -->|exit| X[say goodbye, drop session]
    P --> P1{customer id known?}
    P1 -->|no| P2[ask for it, park the question] --> A
    P1 -->|yes| P3[fetch from postgres] --> P4[answer from real data]
```

this runs as a **LangGraph state machine**, not a chain of if statements. nodes are the handlers, edges are conditional functions that read conversation state and return the next node name. two things fall out of that which would be messy otherwise:

- the **waiting shortcut** at the top. if a handler already asked the customer something, the classifier is skipped entirely. that's one full llm round trip saved, roughly **3 seconds** off a turn where the intent was never in doubt.
- the **retry diversion**. if someone has already failed id verification three times, the personal branch refuses and reroutes to escalate before the handler is even entered. the guard lives in the edge, not buried inside the handler.

---

## the part that isn't a single turn

most voice bot demos answer one question and stop. the harder problem is what happens when you need something from the customer before you can answer them.

ask *"what's my loan outstanding"* with no id on file and this happens:

| turn | what the system does | llm calls | db hits |
|---|---|---|---|
| 1 | classify → personal. no id anywhere in history. **park the question and the conversation snapshot**, ask for the id | 2 | 0 |
| 2 | waiting shortcut fires, classifier skipped. extract `CU001` from *"see you zero zero one"*, validate, fetch, **unpark the original question**, answer it | 2 | 2 |
| 3+ | id is now cached on session state. no extraction, no validation | 1 | 1 |

two bugs that only exist because of that detour, both fixed:

**the question gets lost.** by the time the id arrives, the last thing the customer said is an id, not a question. the original code scanned backwards through history for "a message that doesn't look like an id", which never matched, because nobody says a clean `CU001` out loud, they say *"it's c u zero zero one"*. now the question is parked explicitly on state when the detour starts.

**the context poisons the answer.** grab recent history after verification and the last two turns are always *"please tell me your customer id"* and the customer reading it out. feed that to the model as context and it decides the conversation is about collecting an id, so it asks for the id again instead of answering. fixed by snapshotting history **before** the detour begins, so that exchange physically can't be in scope.

same reason language is detected once at classification and cached on state rather than per handler. on turn 2 the input text is a spoken customer id. you cannot tell someone speaks telugu from hearing *"c u zero zero one"*.

---

## screenshots

<table>
<tr>
<td><img src="assets/img1.png" width="400"></td>
<td><img src="assets/img2.png" width="400"></td>
</tr>
<tr>
<td><img src="assets/img3.png" width="400"></td>
<td><img src="assets/img4.png" width="400"></td>
</tr>
</table>

---

## what i actually measured, not just claimed

ran a real eval harness (`eval_full.py`) through the actual pipeline, real groq calls, real postgres, real chromadb, nothing mocked, on a 95 case labeled test set. raw per-case output is committed as `eval_results.csv`, so every number below can be recomputed from the file rather than taken on trust.

| what | result |
|---|---|
| intent classification accuracy | **95.8%** (91/95) |
| language detection accuracy | **93.7%** (89/95) |
| personal data fetch success | **24/24**, 100% |
| knowledge base retrieval accuracy | **27/30**, 90% |
| escalation routing accuracy | **18/20**, 90% |

per intent, so one weak class can't hide behind a good average:

| intent | correct | n |
|---|---|---|
| smalltalk | 13 | 13 |
| exit | 8 | 8 |
| general | 29 | 30 |
| personal | 23 | 24 |
| escalate | 18 | 20 |

that 90% escalation number only measures whether the classifier routed an escalate-worthy message correctly. it is **not** the real world escalation rate, which also includes things a single message can't show, like someone failing id verification three times in a row, or a knowledge base search coming back empty. those are separate paths into the same handler. kept apart on purpose instead of blended into one number that oversells itself.

---

## where the latency actually goes

measured per stage across the same 95 cases, in seconds:

| stage | p50 | p95 | max | share of a turn |
|---|---|---|---|---|
| intent classification (groq) | **2.968** | 10.197 | 11.182 | ~99% |
| knowledge base search (chromadb) | 0.030 | 0.043 | 0.136 | ~1% |
| account fetch (postgres) | **0.008** | 0.010 | 0.040 | <1% |

worth sitting with that for a second. the database answers in **8 milliseconds** and the vector search in **30**. the model call is **2,968**. retrieval and storage are effectively free here, and any optimisation that isn't about the llm round trip is optimising the wrong 1%.

that's also what justifies the waiting shortcut. skipping one classification isn't a micro-optimisation, it's removing the single dominant cost of the turn.

**about that p95.** the eval fires 95 requests back to back with no spacing, which is a burst pattern that trips groq's rate limiting, and individual calls that normally take 1 to 2 seconds start landing at 8 to 11. the p50 of 2.97s reflects normal behaviour, the p95 of 10.2s reflects the harness hammering the api. real single-user traffic doesn't look like that. reported both rather than quietly publishing the p50 alone.

---

## where it fails, and what the failures mean

there are 10 failures across the whole run. all of them are more interesting than the 95.8%.

### the confidence threshold never actually fires

there's a `CONFIDENCE_THRESHOLD = 0.7` gate that routes anything less certain to a "could you rephrase that" path. across all 95 cases:

| | mean confidence |
|---|---|
| correctly classified | 0.960 |
| **incorrectly** classified | **0.955** |

lowest confidence produced anywhere in the run was **0.90**. the gate never triggered once, and the four wrong answers came in at 0.95, 0.95, 0.95 and 0.97. the model is confidently wrong, not uncertain, so a self-reported confidence score is not a usable safety net here. it stays in as a guard against a genuinely broken response, but it isn't catching the failure mode that actually exists.

### the 4 intent misses

| utterance | labeled | predicted | conf |
|---|---|---|---|
| "what is the minimum balance in my account" | personal | general | 0.97 |
| "how do I file a complaint with the bank" | general | escalate | 0.95 |
| "why is my account frozen" | escalate | general | 0.95 |
| "why was my loan application rejected" | escalate | general | 0.95 |

the second one is arguably a bad label, not a bad prediction. the routing prompt explicitly lists *"is making a complaint"* under escalate, so the model followed the instruction it was given and my ground truth disagreed with my own prompt.

rows 3 and 4 are the real gap. both are *"explain a decision about my account"*, which doesn't fit cleanly into personal, general or escalate. that's a taxonomy problem, not a model problem, and adding a class won't fix it without a clearer boundary first.

### language accuracy is one bucket, not a spread

93.7% is a misleading way to say this:

| language | correct | n |
|---|---|---|
| english | 70 | 70 |
| telugu | 8 | 8 |
| hinglish | 6 | 6 |
| **hindi** | **5** | **11** |

every single failure is hindi, and every one of them is hindi predicted as hinglish. never the reverse, never any other pair. the six inputs:

```
mera account balance kya hai
mera EMI kab due hai
mera loan status kya hai
mera phone number kya hai registered
savings account ke liye minimum balance kitna hai
mera paisa chori ho gaya, complaint karni hai
```

they all contain english loanwords. account, balance, EMI, loan, status, complaint. the prompt defines hinglish as *"the sentence mixes actual hindi words and actual english words together"*, which is exactly what these are. **by my own definition the model is right and my labels are wrong.**

that isn't a free pass, it's a worse problem than a model error, because `state["language"]` drives generation. hindi means reply in devanagari, hinglish means mixed script. the boundary needs a real rule (probably: loanwords that have no common hindi equivalent don't count as code switching) before the 93.7% means anything at all.

### the 3 retrieval misses

`"is there a penalty for not maintaining minimum balance"`, `"what is the daily UPI transaction limit"`, `"can I open an account online without visiting the branch"`.

the metric only checks whether the **top** chunk came from the right section, so a correct answer sitting at rank 2 still counts as a miss. two of the three are likely chunking, not embedding. the chunker splits on a fixed word window with overlap and has no minimum size floor, so a few sections produce a tiny tail fragment that duplicates content already in the previous chunk and competes for the top slot.

---

## what i picked and why

| piece | using | skipped | why |
|---|---|---|---|
| routing | LangGraph state machine | plain if/else dispatch | conditional edges made the waiting shortcut and the retry-to-escalate diversion explicit instead of nested conditions scattered through the handlers |
| LLM | Groq, gpt-oss-120b | llama 3.1 8b, started here | the 8b model kept reading indian english ("kindly do the needful and check my balance") as hindi in roman letters. adding telugu on top of english, hindi and hinglish needed more headroom. llama 3.1 8b is also on groq's retirement list |
| speech to text | browser Web Speech API | server side STT | keeps audio off the wire entirely, no upload round trip in the response path, no per-minute cost. tradeoff is chromium-family browsers only, so there's a text input fallback |
| text to speech | Vachana by Gnani.ai | generic TTS | trained on indian voice data, handles the code switching generic models fumble |
| vector search | ChromaDB, local | Pinecone, Weaviate | 15 chunks. a network hop to a hosted vector db would cost more than the 30ms the whole search currently takes |
| id extraction | LLM prompt | regex | people say ids out loud as "see you zero zero one", "cu double o one", "cu forty five". the variant space is open ended, regex isn't |
| retrieval cutoff | dynamic drop detection | fixed 0.7 threshold | a flat number works on one dataset and lets garbage through on another. this scans for the largest gap in the sorted scores instead, so it adapts to whatever the model's distribution looks like |
| database | Postgres on Neon, pooled | one shared connection, started here | one connection meant every balance check waited in line behind the last one |
| audio delivery | streamed 150ms PCM buffers | wait for the full file | the customer hears the first word while the rest is still being synthesised |

---

## the honest parts

### bugs that only showed up once it was live

<details>
<summary>one shared db connection was quietly making everyone wait</summary>

every personal question hit the same single `psycopg2` connection, and a connection can only run one query at a time, so under real traffic balance checks queued up one by one with nothing looking broken from the outside.

fixed with a pool. borrow, use, hand back.

```python
conn = db_conn.getconn()
try:
    cursor = conn.cursor()
    cursor.execute(query)
finally:
    db_conn.putconn(conn)
```

the `finally` matters more than the pool does. skip it and every failed query leaks a connection until the pool is empty, which is a worse failure than the bottleneck it replaced.

there was a second half to this. neon gives you a direct endpoint and a pooled one (the hostname with `-pooler` in it) and my `.env` pointed at the direct one. switching to pooled fixed neon's ceiling but not mine, because the app still only ever made one connection object. both sides had to change.
</details>

<details>
<summary>circular imports between the router and the handlers</summary>

the intent router needs the handlers, the handlers need constants back from the router, import both at the top of each file and python gets stuck loading them.

fixed by importing inside the function body where it's actually used, never at the top. `smalltalk.py` is the exception and can import at module level, because by the time the router lazily imports it, the router has finished loading.
</details>

<details>
<summary>the blocking calls were freezing every other caller</summary>

`psycopg2` and the groq sdk are both synchronous. calling them directly inside an async endpoint blocks the entire event loop, so one person's balance check stalls everyone else's request on a single worker deployment.

wrapped in `asyncio.to_thread`. easy to miss because it looks completely fine with one user.
</details>

<details>
<summary>the browser refused to play the audio</summary>

asking the tts api for `container=wav` on a streamed response puts a wav header on **every chunk**. concatenate those and you get a file with a dozen headers embedded in the middle of the audio data, which the browser just rejects.

fixed by requesting raw PCM and building one valid header over the whole concatenated stream.

there's a second half on the client. PCM samples are 2 bytes and network chunks don't respect that boundary, so a chunk can end mid-sample. the leftover byte gets carried into the next chunk instead of dropped. get that wrong and you get audio that degrades into static the longer it plays.
</details>

<details>
<summary>fetch() resolves before the audio exists</summary>

`fetch()` returns as soon as **headers** arrive, and FastAPI's StreamingResponse sends 200 OK immediately, before a single byte of audio has been generated. if synthesis then hangs, `await reader.read()` waits forever and there is no exception for a catch block to see.

fixed with a stall timer that resets on every chunk received, rather than a fixed ceiling on total duration. a long legitimate answer doesn't get killed for taking a while, only actual silence does.
</details>

### what's not handled yet

- **sessions live in memory, per instance.** fine as one process, which is what this is deployed as. more than one instance and a caller could land somewhere that never saw their session. the fix is redis, deferred until there's actually a second instance
- **the db pool is per instance too.** three instances means three separate pools hitting neon, not one shared pool of five
- **no otp or email check**, customer id against the database is the only identity gate. fine for a demo, nowhere near enough for anything real
- **no automated test suite.** `eval_full.py` measures accuracy and latency, that's an eval harness, not unit tests. no coverage of the branch logic itself
- **`SELECT *` across joined tables can collide on column names.** `accounts.status` and `loans.status` are both `status`, and `dict(zip(...))` keeps the last one. found it during review, listed here rather than quietly left in
- **the chunker has no minimum size floor**, so sections between 81 and 100 words emit a tail fragment that duplicates the chunk before it
- **a local only playback path exists** for testing on my own machine, never runs on the deployed server

---

## run it yourself

```bash
pip install -r requirements.txt

python scripts/convert_to_jsonl.py    # policy text  →  chunked jsonl
python scripts/knowledge_base.py      # jsonl        →  vector index
python scripts/setup_database.py      # seeds test customers

uvicorn app:app --reload              # http://127.0.0.1:8000/ui
```

or with docker:

```bash
docker build -t banking-voice-agent .
docker run -p 8000:8000 --env-file .env banking-voice-agent
```

`.env` needs `GROQ_API_KEY`, a pooled Neon `DB_HOST` (the one with `-pooler` in it) plus `DB_NAME` `DB_USER` `DB_PASSWORD` `DB_PORT`, and `VACHANA_TTS`.

the vector index is committed to the repo on purpose. render's disk is wiped on every redeploy, so building it locally and shipping it inside the image avoids both a build step and a paid persistent disk.

---

## file layout

```
app.py                    fastapi entry, sessions, /chat /speak /session /health
llm_intent.py             langgraph routing, intent + language classifier
handlers/                 personal, general, escalate, smalltalk
scripts/                  db queries, kb search + drop detection, setup scripts
utils/                    safe json parsing, speech text cleanup
connections/              api keys, pooled db connection, groq client
Gnani_Vachana_TTS/        streaming tts for the browser
data/                     policy source text and chunked jsonl
chroma_db/                prebuilt vector index, committed deliberately
eval_full.py              eval harness
test_set.jsonl            95 labeled cases
eval_results.csv          raw per-case output, so the numbers above are checkable
assets/                   screenshots, demo video
```

---

<div align="center">

[GitHub](https://github.com/niharnandala)

</div>
# Engineering notes

This is the long version. The [README](README.md) is the 30 second pitch, this is everything that actually happened building it, bugs included.

---

## Architecture decisions, in depth

**Why Groq + gpt oss 120b instead of llama 3.1 8b instant**

Started on llama 3.1 8b instant since it's fast and free on Groq. It kept misreading normal, slightly awkward Indian English phrasing ("kindly do the needful and check my balance") as Hindi typed in roman letters, when every word in that sentence is actually English. Adding Telugu detection on top of Hindi/English/Hinglish needed more reasoning depth than an 8b model reliably gives. Moved to gpt oss 120b, which handles the "is this actually English phrased unusually, or actually Hindi" distinction correctly, and isn't on Groq's deprecation list, unlike llama 3.1 8b instant which Groq is retiring mid August 2026.

**Why dynamic drop detection instead of a fixed similarity threshold**

A flat cutoff like 0.7 works great for one embedding model on one dataset and lets garbage through on another, there's no universal number that's correct everywhere. Drop detection looks at the actual shape of the similarity scores instead:

```
scores:   0.91   0.89   0.85   0.61   0.58
gaps:            0.02   0.04   0.24   0.03
                               ^
                        gap of 0.24 beats threshold 0.15
                        cut here, keep only the first 3
```

Always keeps the best result, then walks down the sorted list checking the gap between each consecutive pair. The first gap bigger than the threshold is where real answers end and irrelevant chunks begin. Adapts to whatever shape of scores this model actually produces instead of guessing a number in advance.

**Why LLM based customer id extraction instead of regex**

People say ids out loud on a call in ways regex genuinely cannot handle: "see you zero zero one", "c u 001", "cu double o one". An LLM reading for intent handles all of these the same way a human listening would. Regex reading for a fixed pattern breaks the first time someone phrases it differently than expected.

---

## The database bottleneck, full story

Started with a single `psycopg2.connect()` call in `connections.py`, reused for every request via one shared `db_conn` object. Worked completely fine in local testing, one user, one request at a time.

The problem: a single Postgres connection can only run one query at a time. Every personal intent question, every balance check, every EMI lookup, funnels through `get_customer_full_data()` or `validate_customer_id()` in `queries.py`, both of which hit that same one connection. Under real concurrent traffic, two customers asking about their balance at the same moment don't error out, they just silently queue, one waiting behind the other, even though nothing looks broken from the outside. It's a fast queue since DB lookups are quick, but it's still a hidden single lane bridge every personal request has to cross one at a time.

**Neon specific wrinkle on top of this:** Neon gives you two connection strings for the same database, a direct one straight to Postgres, and a pooled one that runs through PgBouncer on Neon's side. The original `.env` was pointed at the direct endpoint (no `-pooler` in the hostname), which meant not even Neon's own built in pooling was helping. Switching `DB_HOST` to the pooled endpoint fixed the Neon side connection ceiling, but didn't fix the actual bottleneck, since the app still only ever created one `psycopg2` connection object from its own side regardless of which endpoint it pointed at.

**Actual fix, both sides:**

```python
# before, one connection, shared everywhere, one request at a time
db_conn = psycopg2.connect(host=..., ...)
cursor = db_conn.cursor()

# after, a pool, borrow and return
from psycopg2 import pool
db_conn = pool.ThreadedConnectionPool(1, 5, host=..., ...)

conn = db_conn.getconn()
try:
    cursor = conn.cursor()
    cursor.execute(query)
finally:
    db_conn.putconn(conn)
```

The `finally` block matters more than it looks. Skip it, and a handful of failed queries quietly leaks connections out of the pool one at a time until there are none left, which is a worse failure mode than the single connection bottleneck it replaced.

**Still an open tradeoff:** the pool is sized per app instance, min 1 max 5. Fine running as a single Render instance. Scale to 3 instances and that's 3 separate pools, up to 15 real connections hitting Neon, not one shared pool of 5. Worth knowing before turning up instance count.

---

## Bugs that only showed up once this was actually running

<details>
<summary>Thread unsafe audio queue</summary>

`sounddevice` fires the mic callback on its own OS thread, completely outside the asyncio event loop. `asyncio.Queue` is not thread safe. Writing to it directly from that callback thread while the event loop was doing a `get()` on the same queue caused silent data corruption, audio drops, occasional crashes, never reproducible the same way twice, which made it genuinely hard to track down.

```python
# wrong, audio thread touches the queue directly
audio_queue.put_nowait(indata[:, 0].copy())

# right, audio thread asks the event loop to do it instead
_main_loop.call_soon_threadsafe(audio_queue.put_nowait, indata[:, 0].copy())
```
</details>

<details>
<summary>The bot was hearing itself talk</summary>

The local TTS playback path used to fire `Speak()` and return immediately, so the mic reopened while the bot was still mid sentence, and transcribed its own voice as a brand new user question, sending the conversation into a strange loop.

Fixed with a unique marker written to stdout right after each `Speak()` call actually finishes. The listening code waits for that marker to appear before reopening the mic, so audio in and audio out never overlap.
</details>

<details>
<summary>Infinite recursion between the personal handler and the intent classifier</summary>

A failed customer id check sent the conversation back to the intent classifier, which routed back to personal, which asked for the id again, forever, no exit condition anywhere in that loop.

Fixed with a `retry_count` that travels with the conversation state and increments on every bounce. Three failures in a row and it escalates to a human instead of asking a fourth time.
</details>

<details>
<summary>listen_once would just hang forever</summary>

In listen once mode, `receive()` sat blocked inside an `async for event in stream` loop with nothing anywhere to wake it back up once the `done` flag was set elsewhere. The entire listening session would freeze with no error, no timeout, nothing.

Fixed by running `send_audio`, `receive`, and `done.wait()` as three separate tasks raced against each other with `asyncio.wait(..., return_when=FIRST_COMPLETED)`. Whichever one finishes first, the rest get explicitly cancelled instead of sitting there waiting on something that will never happen.
</details>

<details>
<summary>Circular imports between the router and the handlers</summary>

The intent router (`llm_intent.py`) needs to call into the handlers. The handlers need a function back from the router to actually run the whole loop. Importing both at the top level of each file gets Python stuck, A imports B, B imports A, and A is still mid load when B asks for it.

Fixed by importing that one function inside the function body where it's actually used, never at the top of the handler files. Slightly unusual looking in a diff, but it's the standard way to break this specific kind of cycle in Python.
</details>

<details>
<summary>LLM JSON parsing kept crashing the whole request</summary>

Told explicitly to return only JSON, the model would still sometimes wrap the response in a markdown code fence, or add a stray sentence in front of it anyway. A plain `json.loads()` throws on either of those and kills the request outright.

Fixed with one shared `safe_parse_json()` helper, used everywhere a model returns structured output, that strips code fences, strips the word "json" if it snuck in as a label, tries to parse, and falls back to a safe default if it still can't. One place to maintain this instead of three copies quietly drifting apart.
</details>

---

## Eval methodology, in full

`eval_full.py` runs a 95 case labeled test set through the real pipeline pieces, not simulated versions. Real Groq calls for classification, real Postgres fetches for personal cases, real ChromaDB search for general cases.

**What it measures and how:**
- intent classification accuracy, overall and per intent, with a full confusion breakdown
- language detection accuracy, overall and per language
- classify_intent latency, p50 and p95
- for personal cases, a real DB fetch against actually seeded customers, success rate and latency
- for general cases, whether the top returned chunk actually comes from the section labeled correct, not just whether classification was correct
- escalation classification rate, deliberately labeled as exactly that and nothing more

**The honest caveat baked directly into the script itself:** the escalation number measures whether the classifier routed an escalate worthy message to escalate correctly. It is explicitly not the same thing as the real world escalation rate, which also includes situations a single classified message can't show on its own, like a customer failing id verification three times, or a genuine general question that the knowledge base just doesn't cover. Kept these two numbers separate on purpose rather than blending them into one metric that reads better than it should.

**Why the script has a `--delay` flag:** running 95+ requests back to back with zero spacing is a burst pattern that can trip Groq's own rate limiting, which shows up as individual calls occasionally taking 8 to 12 seconds instead of the normal 1 to 2, not because the model is actually slow, but because requests are queuing or retrying behind the scenes. That burst pattern also isn't realistic anyway, real callers are naturally spaced out by conversation and TTS playback. `--delay` adds spacing between test cases so the latency numbers reflect realistic pacing instead of an artificial traffic spike. The p50 of 2.97s vs p95 of 10.2s in the actual results reflects exactly this, most calls are fast, a handful queue behind Groq's own rate limiting.

**Actual results from the last run, 95 cases:**

```
personal    23 / 24  correct
general     29 / 30  correct
escalate    18 / 20  correct
smalltalk   13 / 13  correct
exit         8 / 8   correct
```

---

## Deployment reasoning, Render specifically

**Why Docker instead of Render's native Python buildpack:** the project already needed a specific build order, torch installed from the CPU only wheel index before the rest of requirements.txt, so a plain buildpack detecting "this is Python" and running a generic install wouldn't have gotten that right without extra config anyway. A Dockerfile gives full control over that build order directly.

**Why Standard tier (2GB RAM) over Free or Starter (512MB each):** the stack loads `torch`, `sentence-transformers`, the embedding model itself, and ChromaDB all into memory at startup, on top of FastAPI and uvicorn. That combination routinely sits at 500MB to 1GB+ before a single request even comes in. Both Free and Starter cap at 512MB, real risk of the container getting OOM killed the moment it boots and tries to load the embedding model. Confirmed actual memory usage against the metrics tab before committing to a tier, rather than guessing and overpaying upfront.

**Why chroma_db is committed straight into the repo instead of built on a Render disk:** Render's default web service disk is ephemeral, wiped on every redeploy. Building the knowledge base once locally and committing the resulting `chroma_db/` folder means it ships inside the Docker image via `COPY . .`, no separate build step needed on Render's side, no persistent disk to manage or pay for.

**Before pushing anything, checked whether real secrets had ever been committed:**

```bash
git log --all --full-history -- .env
```

Empty output confirms `.env` itself was never tracked, at any point in the repo's history, so no history rewriting was needed. Worth running this on any project before assuming `.gitignore` alone is enough, since gitignore only stops *future* commits from tracking a file, it does nothing for something already committed in the past.

---

## Known limitations, full list

- **Sessions live in memory, per app instance.** `sessions = {}` in `app.py` is a plain Python dict. Fine running as a single process, which is what this is deployed as. Scale to more than one worker or instance and a caller's session can land on an instance that never created it, since each instance has its own separate memory. The real fix would be something like Redis backed sessions, not worth building until there's actually more than one instance running.
- **The DB pool is sized per instance**, min 1 max 5. Multiple instances mean multiple separate pools hitting Neon, not one shared pool.
- **No OTP or email verification.** Customer id checked against the database is the only identity gate right now.
- **No automated test suite.** `eval_full.py` is a real eval harness measuring accuracy and latency against a labeled set, that's a different thing from unit tests covering the code paths themselves.
- **A local only playback path exists**, `speak()` and `_play_audio()` inside `vachana_tts.py`, for testing TTS output through actual speakers on a development machine. Needs a real audio device via `sounddevice`, never runs on the deployed server, only ever called from a local script.
- **`SELECT *` across joined tables in `queries.py` can silently collide on column names.** Both the accounts table and the loans table have a column named `status`. `dict(zip(column_names, row))` with duplicate keys keeps the last one, so the account's own status can get silently overwritten by the loan's status in the returned data. Caught this during review, worth fixing with explicit column aliases before it matters in a real scenario where the two actually differ.
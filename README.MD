# Banking Voice Agent with Intelligent Routing

## The Business Problem First

Every human handled bank call in India costs ₹25 to ₹75 fully loaded.

Not just the agent salary. Infrastructure. Training. Management overhead. All of it.

10,000 calls a day. Do the math.

And most of those calls are the same four things — balance check, EMI status, policy question, or "I need to talk to someone." Routine. Repetitive. Expensive.

This project handles those four automatically. No human agent needed for the routine ones. Human agents only get pulled in when something actually needs them.

That is the business case. ₹75 per call down to ₹9. At scale that difference is not small.

---

## Why This Exists

Most AI voice agents being built right now are LLM wrappers.

```
🎤 User speaks  →  📦 dump everything into one prompt  →  🤞 hope for the best
```

No intent routing. No structured fallback. No cost control on tokens. Every single query goes through the full LLM whether it needs to or not.

At 10,000 calls a day that token cost adds up fast.

On top of that most of these agents are built on Whisper or Google STT. Both trained mostly on foreign English. Indian customers do not speak that way on a phone call. They pause differently. They mix words differently. They spell out things like "see you zero zero one" when they mean CU001.

Foreign trained STT fails on this. Constantly.

So there were two real problems worth solving:

One — token cost exploding because everything goes through the LLM blindly.

Two — STT failing on how Indians actually speak.

This project solves both.

---

## How It Works and Why Every Decision Was Made This Way

```
🎤 Customer speaks
        ↓
🧠 Vachana STT decodes the audio
        ↓
⚡ Intent classifier runs first
        ↓
        ├── 💰 Balance / EMI / Loan   →  hits PostgreSQL directly
        ├── 📋 Policy / FAQ           →  searches ChromaDB knowledge base
        ├── 🚨 Complex request        →  raises a structured staff ticket, stops
        └── ❓ Unclear input          →  resets and continues
```

**Why Vachana STT and not Whisper**

Vachana is built by Gnani.ai and trained on Indian voice data across BFSI specifically. It handles the way Indians actually speak on phone calls — the pauses, the Hinglish mixing, the spelled out customer IDs. Whisper struggles with this. Vachana does not.

**Why intent classification runs before anything else**

If someone asks their balance you do not need to search the knowledge base. If someone asks a policy question you do not need to hit the database. Classifying first means only the right thing runs. Nothing extra. Tokens stay controlled and the response is faster because you are not doing unnecessary work.

**Why PostgreSQL for personal queries and not the LLM**

The LLM does not know your balance. It cannot know. It makes things up. For anything personal — balance, EMI, loan — the only right answer is to hit the actual database and return the actual number. The LLM just formats the response after the data is fetched. It never guesses.

**Why ChromaDB with dynamic drop detection and not a fixed threshold**

Standard RAG pipelines set a fixed similarity threshold like 0.7 and call it done. The problem is 0.7 means different things for different queries and different models. Sometimes 0.65 is excellent. Sometimes 0.82 is mediocre.

Dynamic drop detection looks at the shape of the scores instead. If scores are 0.91, 0.88, 0.85, 0.61, 0.58 — the gap between 0.85 and 0.61 is the signal. Cut there. Keep the first three. The system adapts to whatever the query produces instead of trusting a number someone picked manually.

**Why there is a retry limit and a clean escalation path**

Most bots either answer everything confidently including wrong answers, or they crash and loop forever when confused. Neither is acceptable in banking.

This system has a confidence threshold. If the LLM is not sure enough it asks again. If after three tries it still cannot get a valid customer ID it stops, raises a ticket, and hands off to a human. It knows its own limits. That is not a weakness. In banking that is exactly what you want.

**Why the mic is muted while the bot is speaking**

Without this the bot hears its own voice through the microphone, transcribes it as a new user query, and responds to itself. That loop runs forever. The mic mutes the moment the bot starts speaking and only opens again after speech is fully finished — confirmed by a stdout marker from PowerShell, not a timer guess.

**Why audio queue uses call_soon_threadsafe**

sounddevice runs the mic callback on a completely separate OS thread. asyncio.Queue is not thread safe. If you call put_nowait directly from that thread while the event loop is doing a get on the same queue you get race conditions — corrupted data, dropped audio chunks, weird bugs that only happen sometimes and are nearly impossible to reproduce. call_soon_threadsafe hands the audio chunk back to the event loop thread which then puts it in the queue safely on its own turn.

---

## What Makes This Different From the 1000 Other Voice Agent Projects

You have seen voice agent projects. Everyone has one now.

Here is what most of them do not have:

**Real data. Not a mock.**
This hits an actual PostgreSQL database with real customer records. Not hardcoded responses. Not a fake API. When the bot says your balance is 25000 it got that number from a real database query.

**A system that knows when to stop.**
Most demo projects answer everything. This one has a confidence threshold, a retry counter, and a structured escalation path that raises a ticket with conversation context for the staff member who picks it up. Building something that fails gracefully is harder than building something that answers confidently and wrong.

**Token cost awareness built into the architecture.**
The 4 way routing is not just about speed. It is about cost. General policy questions go to ChromaDB. Personal queries go to PostgreSQL. The LLM only gets called for what it actually needs to do — intent classification and response generation. Not retrieval. Not data lookup. That discipline matters at scale.

**Production minded error handling throughout.**
Every API call is wrapped in try/except with a safe fallback. Every database call checks if the result is None before trusting it. The STT reconnect loop checks a stop flag before retrying so it does not crash with "cannot schedule new futures" after the call ends. These are the things that break in production that demo projects never think about.

---

## Project Structure

```
Banking-Voice-Agent/
│
├── app.py                  # Streamlit frontend — browser mic + live pipeline logs
├── llm_intent.py           # Intent classification and routing brain
├── vachana.py              # Audio pipeline — STT streaming, TTS, mic handling
├── knowledge_base.py       # ChromaDB setup and vector search with drop detection
├── queries.py              # PostgreSQL queries — customer data fetch and validation
├── connections.py          # API keys and DB connection setup
├── setup_database.py       # Creates and seeds the PostgreSQL database
├── bank_policies.jsonl     # Knowledge base source — bank policy chunks
├── convert_to_jsonl.py     # Converts raw policy text to JSONL format
│
├── handlers/
│   ├── personal.py         # Handles balance, EMI, loan queries — hits PostgreSQL
│   ├── general.py          # Handles policy questions — searches ChromaDB
│   ├── escalate.py         # Raises structured ticket for complex requests
│   └── smalltalk.py        # Resets conversation and reintroduces bot
│
└── chroma_db/              # Persisted ChromaDB vector store
```

---

## Stack

| Layer | Technology | Why |
|---|---|---|
| Speech to Text | Gnani Vachana STT | Trained on Indian voice data |
| LLM | Groq LLaMA 3 | Sub-second response times |
| Vector Database | ChromaDB | Persistent, local, fast |
| Relational Database | PostgreSQL | Real customer data |
| Frontend | Streamlit | Live pipeline visibility in browser |
| Language | Python async | Non-blocking audio + API calls |

---

## How to Run

**1. Clone the repo**
```bash
git clone https://github.com/niharnandala/Banking_Voice_Agent_With_intelligent_Routing
cd Banking_Voice_Agent_With_intelligent_Routing
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Set up environment variables**

Create a `.env` file:
```
VACHANA_API_KEY=your_vachana_key
GROQ_API_KEY=your_groq_key
DB_HOST=your_db_host
DB_NAME=your_db_name
DB_USER=your_db_user
DB_PASSWORD=your_db_password
```

**4. Set up the database**
```bash
python setup_database.py
```

**5. Build the knowledge base**
```bash
python knowledge_base.py
```

**6. Run via Streamlit**
```bash
streamlit run app.py
```

Or run directly in terminal:
```bash
python llm_intent.py
```

---

## What Is Still Being Built

```
✅ Core voice pipeline
✅ Intent routing — 4 handlers
✅ PostgreSQL integration — live customer data
✅ ChromaDB RAG — dynamic drop detection
✅ Streamlit frontend — live pipeline logs in browser
✅ Error handling — every API call and DB call wrapped
✅ Customer ID validation — against real database
🔄 Vachana TTS — in progress, contacted Gnani team
🔄 FastAPI deployment
🔄 Hindi and Hinglish support
```

---

Built with [@Gnani.ai](https://gnani.ai) Vachana STT
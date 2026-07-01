import re
import json
import asyncio
from vachana import listen, speak, run_timer
from connections import groq_client
from queries import get_customer_full_data


# ── PROMPTS ────────────────────────────────────────────────────────────────────

id_prompt = """
We are currently expecting the user to provide their customer id.
Customer ids follow the pattern CU followed by 3 digits, like CU001, CU002, CU045.

People often say this out loud in broken or spelled out ways due to speech-to-text errors, for example:
- "it is c u 001" means CU001
- "c u zero zero one" means CU001
- "cu 045" means CU045
- "see you double o one" means CU001

Be flexible and extract the id even if spacing, capitalization, or spelled-out numbers are used.
If you can reasonably tell what the customer id is meant to be, extract it in the standard format CUxxx.

Reply with ONLY valid JSON in this exact format, nothing else:
{{"has_id": true, "customer_id": "CU001"}}
or
{{"has_id": false, "customer_id": null}}

User said: {text}
"""

data_answer_prompt = """
You are a banking voice assistant. Answer the customer's question
using ONLY the customer data provided below.

Customer data:
{data}

Rules:
- Reply in plain spoken sentences only
- No bullet points, no bold, no markdown formatting of any kind
- Keep it short, like you are speaking out loud to someone on a phone call
- Do not make up anything not present in the customer data above
"""


# ── HELPERS ────────────────────────────────────────────────────────────────────

def _safe_parse_json(raw_text, fallback):
    # LLMs sometimes wrap JSON in ```json fences even when told not to.
    # This strips that wrapping and falls back safely instead of crashing.
    cleaned = raw_text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[warning] could not parse LLM JSON: {e!r}, raw was: {raw_text!r}")
        return fallback


def clean_for_speech(text):
    # safety net in case LLM ignores prompt rules and adds markdown anyway
    # removes ** bold **, * italic *, bullet points, and extra whitespace
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'^\s*[-•]\s*', '', text, flags=re.MULTILINE)
    text = ' '.join(text.split())
    return text


# ── MAIN HANDLER ───────────────────────────────────────────────────────────────

async def handle_personal(conversation_history, retry_count=0):

    # step 1: ask the user for their customer id
    await speak("Please tell me your customer id.")
    conversation_history.append({"role": "assistant", "content": "please tell your customer id"})

    # step 2: listen to what they say
    user_text = await listen()
    conversation_history.append({"role": "user", "content": user_text})

    # step 3: send what they said to LLM to extract the customer id
    check_stop  = asyncio.Event()
    check_timer = asyncio.create_task(run_timer("checking your id", check_stop))

    id_response = groq_client.chat.completions.create(
        model    = "llama-3.1-8b-instant",
        messages = [
            {"role": "system", "content": id_prompt.format(text=user_text)},
            {"role": "user",   "content": user_text}
        ]
    )

    check_stop.set()
    await check_timer

    # step 4: parse the LLM reply safely
    raw_id_result = id_response.choices[0].message.content
    fallback      = {"has_id": False, "customer_id": None}
    id_result     = _safe_parse_json(raw_id_result, fallback)

    # step 5a: id found — fetch data and answer the original question
    if id_result.get("has_id"):
        customer_id = id_result.get("customer_id")
        print(f"\ncustomer_id: {customer_id}\n")

        await speak("Thank you, got it.")
        conversation_history.append({"role": "assistant", "content": f"got customer id: {customer_id}"})

        # fetch this customer's real data from the database
        data = get_customer_full_data(customer_id)

        # ask LLM to answer the user's original question using that data
        answer_stop  = asyncio.Event()
        answer_timer = asyncio.create_task(run_timer("fetching your answer", answer_stop))

        answer_response = groq_client.chat.completions.create(
            model    = "llama-3.1-8b-instant",
            messages = [
                # system: rules + customer data baked in
                {"role": "system", "content": data_answer_prompt.format(data=data)},

                # middle: full conversation so far (so LLM knows what was asked)
                *conversation_history,

                # last: the user's original question
                {"role": "user", "content": user_text}
            ]
        )

        answer_stop.set()
        await answer_timer

        # extract the reply text, clean it, speak it
        raw_reply    = answer_response.choices[0].message.content
        clean_reply  = clean_for_speech(raw_reply)

        conversation_history.append({"role": "assistant", "content": raw_reply})
        print(f"\nbot: {clean_reply}\n")
        await speak(clean_reply)

    # step 5b: id not found — send back to intent router, bump the retry counter
    else:
        # imported here (not at top) to avoid circular import:
        # llm_intent.py imports personal.py, so personal.py can't import
        # llm_intent.py at the top level — Python would get stuck in a loop
        from llm_intent import run_intent
        await run_intent(conversation_history, user_text, retry_count=retry_count + 1)
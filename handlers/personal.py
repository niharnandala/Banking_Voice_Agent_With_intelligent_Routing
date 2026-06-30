import json
import asyncio
from vachana import listen, speak, run_timer
from connections import groq_client

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


def _safe_parse_json(raw_text, fallback):
    """
    Same defensive parsing as llm_intent.py - strips accidental markdown
    fences and falls back instead of raising if the model returns
    something that isn't valid JSON.
    """
    cleaned = raw_text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[warning] could not parse LLM JSON output: {e!r}, raw was: {raw_text!r}")
        return fallback


async def handle_personal(conversation_history, retry_count=0):
    """
    retry_count: FIX - passed in from run_intent() and passed back out if we
    have to re-classify. Without this, a user who never gives a valid id
    could bounce between here and run_intent() forever (recursion bug).
    """
    await speak("Please tell me your customer id.")  # FIX: speak is now async, must be awaited
    conversation_history.append({"role": "ai", "content": "please tell your customer id"})

    text = await listen()
    conversation_history.append({"role": "user", "content": text})

    check_stop  = asyncio.Event()
    check_timer = asyncio.create_task(run_timer("checking your id", check_stop))

    response = groq_client.chat.completions.create(
        model    = "llama-3.1-8b-instant",
        messages = [
            {"role": "system", "content": id_prompt.format(text=text)},
            {"role": "user",   "content": text}
        ]
    )

    check_stop.set()
    await check_timer

    raw = response.choices[0].message.content
    # FIX: safe fallback if model output isn't valid JSON - treat as "no id found"
    # instead of crashing the whole call with an uncaught exception.
    fallback = {"has_id": False, "customer_id": None}
    result = _safe_parse_json(raw, fallback)

    if result.get("has_id"):
        customer_id = result.get("customer_id")
        await speak("Thank you, got it.")
        conversation_history.append({"role": "ai", "content": f"got customer id: {customer_id}"})
        print(f"\ncustomer_id: {customer_id}\n")
        # NOTE: this is where you'd actually validate customer_id against
        # your real customer database before trusting it - right now any
        # string matching the CUxxx shape is accepted as-is.

    else:
        # FIX: bump retry_count and pass it along. run_intent() will stop
        # looping and escalate to a human once MAX_INTENT_RETRIES is hit,
        # instead of recursing through run_intent <-> handle_personal forever.
        from llm_intent import run_intent
        await run_intent(conversation_history, text, retry_count=retry_count + 1)
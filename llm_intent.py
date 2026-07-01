# llm_intent.py

import asyncio
import json
from vachana import listen, greet, speak, run_timer
from connections import groq_client


intent_prompt = """
You are an intent classifier for a banking voice agent.
Classify the user query into exactly one of these:
- general: bank policies, EMI policies, how to open account, public info
- personal: balance, EMI due date, loan amount, personal account data
- smalltalk: greetings, rubbish, not related to banking at all
- escalate: modifying something, complex request, needs staff help

Reply with ONLY valid JSON in this exact format, nothing else:
{"intent": "personal", "confidence": 0.85}
"""

# FIX: confidence cutoff was a strict ">" before, so a model returning exactly
# 0.7 fell through to the "I'm not sure" branch even though 0.7 was meant to
# count as "confident enough". Using >= fixes that boundary case.
CONFIDENCE_THRESHOLD = 0.7

# FIX: cap on how many times we'll bounce back into intent classification for
# the SAME ongoing personal-id flow, so a confused loop can't recurse forever
# (see handlers/personal.py). 0 means "no retries used yet".
MAX_INTENT_RETRIES = 3


def _safe_parse_json(raw_text, fallback):
    """
    LLMs that are told 'reply with ONLY JSON' sometimes still wrap the
    answer in ```json fences or add a stray word. This strips common
    wrapping and falls back gracefully instead of raising and crashing
    the whole call.
    """
    cleaned = raw_text.strip()

    # strip markdown code fences if present, e.g. ```json { ... } ```
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


async def classify_intent(chat_history):
    history_text = "\n".join(f"{m['role']}: {m['content']}" for m in chat_history)

    response = groq_client.chat.completions.create(
        model    = "llama-3.1-8b-instant",
        messages = [
            {"role": "system", "content": intent_prompt},
            {"role": "user",   "content": history_text}
        ]
    )

    raw = response.choices[0].message.content
    # FIX: safe fallback if the model returns garbage - treat as low
    # confidence "smalltalk" so the caller's normal "not sure" path handles it,
    # instead of raising a KeyError/JSONDecodeError and killing the call.
    fallback = {"intent": "smalltalk", "confidence": 0.0}
    return _safe_parse_json(raw, fallback)


async def run_intent(conversation_history, text, retry_count=0):
    """
    retry_count: FIX - tracks how many times we've already bounced through
    here for the same unresolved personal-id flow. Prevents infinite
    recursion between run_intent() <-> handle_personal().
    """
    conversation_history.append({"role": "user", "content": text})

    await speak("Let me check that for you.")  # FIX: now awaited (speak is async)

    classify_stop  = asyncio.Event()
    classify_timer = asyncio.create_task(run_timer("finding your intent", classify_stop))

    result = await classify_intent(conversation_history)

    classify_stop.set()
    await classify_timer

    # FIX: defensive .get() instead of result["intent"] / result["confidence"]
    # so a malformed/partial JSON response can't crash this with a KeyError.
    intent     = result.get("intent", "smalltalk")
    confidence = result.get("confidence", 0.0)

    conversation_history.append({"role": "assistant", "content": f"found intent: {intent}, confidence: {confidence}"})
    print(f"\nintent: {intent}, confidence: {confidence}\n")

    if intent == "personal" and confidence >= CONFIDENCE_THRESHOLD:
        if retry_count >= MAX_INTENT_RETRIES:
            # FIX: stop looping forever, hand off to a human instead
            await speak("I'm having trouble verifying your identity. Let me connect you to a staff member.")
            print("sending to escalate.py (max retries hit)")
            return

        from handlers.personal import handle_personal
        await handle_personal(conversation_history, retry_count=retry_count)

    elif intent == "general" and confidence >= CONFIDENCE_THRESHOLD:
        print("sending to general.py")

    elif intent == "smalltalk" and confidence >= CONFIDENCE_THRESHOLD:
        print("sending to smalltalk.py")

    elif intent == "escalate" and confidence >= CONFIDENCE_THRESHOLD:
        print("sending to escalate.py")

    else:
        await speak("I'm not sure I understood that, could you repeat?")


async def main():
    conversation_history = [
        {"role": "assistant", "content": "Hello, welcome to XYZ Bank. I am your bank assistant. Ask me anything about your account."}
    ]

    await greet()  # FIX: greet() is async now too
    text = await listen()

    await run_intent(conversation_history, text)


if __name__ == "__main__":
    asyncio.run(main())
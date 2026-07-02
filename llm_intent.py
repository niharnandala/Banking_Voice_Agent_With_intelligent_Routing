# llm_intent.py
import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "handlers"))

import asyncio
import json
from vachana import listen, greet, speak, run_timer
from connections import groq_client

# imported at top level so knowledge_base.py loads ONCE when program starts
# never reloads the embedding model again after that


intent_prompt = """
You are an intent classifier for a banking voice agent.
Classify the user query into exactly one of these:
- general: bank policies, EMI policies, how to open account, public info
- personal: balance, EMI due date, loan amount, personal account data
- smalltalk: greetings, rubbish, not related to banking at all
- escalate: modifying something, complex request, needs staff help
- exit: user wants to end the call, says bye, no thanks, stop, that's fine, goodbye

Reply with ONLY valid JSON in this exact format, nothing else:
{"intent": "personal", "confidence": 0.85}
"""

CONFIDENCE_THRESHOLD = 0.7
MAX_INTENT_RETRIES   = 3


def _safe_parse_json(raw_text, fallback):
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


async def classify_intent(chat_history):
    history_text = "\n".join(f"{m['role']}: {m['content']}" for m in chat_history)

    response = groq_client.chat.completions.create(
        model    = "llama-3.1-8b-instant",
        messages = [
            {"role": "system", "content": intent_prompt},
            {"role": "user",   "content": history_text}
        ]
    )

    raw      = response.choices[0].message.content
    fallback = {"intent": "smalltalk", "confidence": 0.0}
    return _safe_parse_json(raw, fallback)


async def run_intent(conversation_history, text, retry_count=0):

    conversation_history.append({"role": "user", "content": text})

    await speak("Let me check that for you.")

    classify_stop  = asyncio.Event()
    classify_timer = asyncio.create_task(run_timer("finding your intent", classify_stop))

    result = await classify_intent(conversation_history)

    classify_stop.set()
    await classify_timer

    intent     = result.get("intent",     "smalltalk")
    confidence = result.get("confidence", 0.0)

    conversation_history.append({"role": "assistant", "content": f"found intent: {intent}, confidence: {confidence}"})
    print(f"\nintent: {intent}, confidence: {confidence}\n")

    if intent == "exit" and confidence >= CONFIDENCE_THRESHOLD:
        await speak("Thank you for calling XYZ Bank. Have a great day. Goodbye.")
        return "exit"   # caught in main() to break the loop

    elif intent == "personal" and confidence >= CONFIDENCE_THRESHOLD:
        from handlers.personal  import handle_personal

        if retry_count >= MAX_INTENT_RETRIES:
            await speak("I'm having trouble verifying your identity. Let me connect you to a staff member.")
            from handlers.escalate  import handle_escalate

            return await handle_escalate(conversation_history, text)
            return "exit"   # call ends after ticket is raised, staff takes over

            return
        await handle_personal(conversation_history, retry_count=retry_count)

    elif intent == "general" and confidence >= CONFIDENCE_THRESHOLD:
        from handlers.general   import handle_general

        await handle_general(conversation_history, text)

    elif intent == "smalltalk" and confidence >= CONFIDENCE_THRESHOLD:
        from handlers.smalltalk import handle_smalltalk

        await handle_smalltalk(conversation_history)

    elif intent == "escalate" and confidence >= CONFIDENCE_THRESHOLD:
        from handlers.escalate  import handle_escalate

        return await handle_escalate(conversation_history, text)
        return "exit"   # call ends after ticket is raised, staff takes over


    else:
        await speak("I'm not sure I understood that, could you repeat?")


async def main():
    conversation_history = [
        {"role": "assistant", "content": "Hello, welcome to XYZ Bank. I am your bank assistant. Ask me anything about your account."}
    ]

    await greet()

    while True:
        text = await listen()

        if not text:
            continue

        result = await run_intent(conversation_history, text)

        if result == "exit":
            break   # FIX: now actually catches the return value and stops

    

if __name__ == "__main__":
    asyncio.run(main())
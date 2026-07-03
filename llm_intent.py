import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "handlers"))
# i add the handlers folder to Python's search path here at the very top
# before any other imports happen
# this means when any file does "from handlers.personal import..."
# Python knows where to look
# i do this once here so i dont need sys.path.append in every handler file

import asyncio
import json
from vachana import listen, greet, speak, run_timer
from connections import groq_client
# i import listen to capture user speech
# greet to speak the welcome message at startup
# speak to voice any response
# run_timer to show live progress in the terminal
# groq_client is my connection to the Groq LLM API


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
# i defined five intents that cover every possible type of call
# general is for public bank information anyone can know
# personal is for account specific data that needs customer id verification
# smalltalk catches anything unrelated so i can reset and restart cleanly
# escalate is for things too complex for the bot to handle
# exit catches goodbye phrases so i can end the call properly
# i ask for confidence too so i can ignore low confidence guesses

CONFIDENCE_THRESHOLD = 0.7
# i set this to 0.7 meaning the LLM needs to be at least 70% sure
# before i act on an intent
# i use >= not > so that exactly 0.7 also counts as confident enough

MAX_INTENT_RETRIES = 3
# this is my safety limit for how many times the personal flow
# can bounce back here without successfully getting a customer id
# once this limit hits i stop the loop and escalate to a human


def _safe_parse_json(raw_text, fallback):
    # i need this because even when i tell the LLM to return ONLY JSON
    # it sometimes wraps it in markdown or adds a sentence before it
    # instead of crashing when that happens i handle it here cleanly

    cleaned = raw_text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    # i strip backtick fences if the LLM added them
    # then strip the word "json" if it appears right after the fences
    # then strip whitespace again to get the clean JSON string

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[warning] could not parse LLM JSON output: {e!r}, raw was: {raw_text!r}")
        return fallback
    # if parsing fails i return the fallback instead of crashing
    # the caller always provides a safe fallback for exactly this situation


async def classify_intent(chat_history):
    history_text = "\n".join(f"{m['role']}: {m['content']}" for m in chat_history)
    # i flatten the full conversation history into one text block
    # each line is "role: content" so the LLM can read the whole conversation
    # and classify the intent based on full context not just the last message

    try:
        response = groq_client.chat.completions.create(
            model    = "llama-3.1-8b-instant",
            messages = [
                {"role": "system", "content": intent_prompt},
                {"role": "user",   "content": history_text}
            ]
        )
        raw = response.choices[0].message.content

    except Exception as e:
        # if Groq is down or the API call fails
        # i return a safe fallback instead of crashing the whole call
        print(f"[error] classify_intent LLM call failed: {e}")
        return {"intent": "smalltalk", "confidence": 0.0}
    # i chose smalltalk with 0.0 confidence as the fallback
    # because 0.0 is below my threshold so it falls into the
    # "not sure, could you repeat" branch which is the safest response

    fallback = {"intent": "smalltalk", "confidence": 0.0}
    return _safe_parse_json(raw, fallback)


async def run_intent(conversation_history, text, retry_count=0):
    # retry_count is passed through from personal.py when the user
    # fails to provide a valid customer id and bounces back here
    # i check it against MAX_INTENT_RETRIES to stop infinite loops

    conversation_history.append({"role": "user", "content": text})
    # i add the user's text to history before classifying
    # so the LLM sees the full conversation including this latest message

    await speak("Let me check that for you.")
    # i speak immediately so the user hears something while i
    # make the API call — prevents awkward silence

    classify_stop  = asyncio.Event()
    classify_timer = asyncio.create_task(run_timer("finding your intent", classify_stop))

    result = await classify_intent(conversation_history)
    # i pass the full conversation history so the classifier
    # understands follow-up questions correctly

    classify_stop.set()
    await classify_timer

    intent     = result.get("intent",     "smalltalk")
    confidence = result.get("confidence", 0.0)
    # i use .get() with defaults here not result["intent"]
    # because if the key is missing .get() gives me the default
    # and result["intent"] would throw a KeyError and crash

    conversation_history.append({"role": "assistant", "content": f"found intent: {intent}, confidence: {confidence}"})
    print(f"\nintent: {intent}, confidence: {confidence}\n")

    if intent == "exit" and confidence >= CONFIDENCE_THRESHOLD:
        await speak("Thank you for calling XYZ Bank. Have a great day. Goodbye.")
        return "exit"
        # i check exit first before everything else
        # i return the string "exit" as a signal to main()
        # so the while loop knows to break and stop listening

    elif intent == "personal" and confidence >= CONFIDENCE_THRESHOLD:
        if retry_count >= MAX_INTENT_RETRIES:
            # user has failed to give a valid id too many times
            # i stop the loop and hand off to a human
            await speak("I'm having trouble verifying your identity. Let me connect you to a staff member.")
            from handlers.escalate import handle_escalate
            await handle_escalate(conversation_history, text)
            return "exit"
            # i return "exit" here too because after escalation
            # there is no point in continuing to listen

        from handlers.personal import handle_personal
        await handle_personal(conversation_history, retry_count=retry_count)
        # i import inside the if block not at the top of the file
        # this is lazy importing — knowledge_base only loads
        # if a general question actually comes in
        # if the user only asks personal questions, general never loads

    elif intent == "general" and confidence >= CONFIDENCE_THRESHOLD:
        from handlers.general import handle_general
        await handle_general(conversation_history, text)

    elif intent == "smalltalk" and confidence >= CONFIDENCE_THRESHOLD:
        from handlers.smalltalk import handle_smalltalk
        await handle_smalltalk(conversation_history)
        # smalltalk clears the history and reintroduces the bot
        # so the next question starts fresh

    elif intent == "escalate" and confidence >= CONFIDENCE_THRESHOLD:
        from handlers.escalate import handle_escalate
        await handle_escalate(conversation_history, text)
        return "exit"
        # after raising a ticket the call ends
        # staff takes over from here so i stop listening

    else:
        await speak("I'm not sure I understood that, could you repeat?")
        # this catches anything below the confidence threshold
        # the while loop in main() continues naturally after this
        # so the bot goes back to listening automatically


async def main():
    conversation_history = [
        {"role": "assistant", "content": "Hello, welcome to XYZ Bank. I am your bank assistant. Ask me anything about your account."}
    ]
    # i seed the history with the opening message
    # so the LLM always knows how the conversation started
    # even on the very first classification

    await greet()
    # greet() speaks the welcome message out loud
    # i await it so the mic only opens after the bot finishes talking

    while True:
        text = await listen()
        # i wait here until the user speaks and goes silent
        # listen() returns the full transcribed sentence as a string

        if not text:
            continue
        # if listen() returned empty string (user said nothing or STT failed)
        # i skip this iteration and go back to listening

        result = await run_intent(conversation_history, text)
        # run_intent handles classification and routes to the right handler
        # it returns "exit" if the call should end, None otherwise

        if result == "exit":
            break
        # if i got "exit" back i break the while loop
        # which ends the program cleanly


if __name__ == "__main__":
    asyncio.run(main())
    # asyncio.run() starts the event loop and runs main() inside it
    # everything async in this project runs inside this one event loop
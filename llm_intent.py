import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "handlers"))
# i add the handlers folder to Python's search path here at the very top
# before any other imports happen
# this means when any file does "from handlers.personal import..."
# Python knows exactly where to look
# i do this once here so i dont need sys.path.append in every handler file

import asyncio
import json
from vachana_stt.vachana import listen, greet, speak, run_timer
from connections.connections import groq_client
from utils.utils import safe_parse_json
# i import listen to capture user speech
# greet to speak the welcome message at startup
# speak to voice any bot response
# run_timer to show live progress in the terminal
# groq_client is my connection to the Groq LLM API
# safe_parse_json from utils.py — one shared function for both files


intent_prompt = """
You are an intent classifier for a banking voice agent in India.

The user may speak in English, Hindi, Telugu, Hinglish (Hindi+English mixed), or Tenglish (Telugu+English mixed).
Classify based on the MEANING of what they said, not the language they said it in.
Even if the transcription looks broken or partially spelled out, try your best to understand the intent.

Classify the user query into EXACTLY one of these five intents:

1. personal
   - User is asking about their own account information
   - Examples: balance, loan amount, EMI due date, transaction history, account number, loan status
   - Hindi examples: "mera balance kya hai", "mera loan kitna bacha hai", "EMI kab kategi"
   - Telugu examples: "naa balance cheppandi", "naa loan entha undi", "EMI epudu kattatam"
   - Hinglish: "my balance kitna hai", "loan amount batao"
   - IMPORTANT: only classify as personal if they are asking about THEIR OWN account data
   - Do NOT classify as personal if they are asking general policy questions

2. general
   - User is asking about bank policies, products, or procedures that apply to everyone
   - Examples: how to open account, what documents needed, interest rates, EMI policies, late payment charges, how mobile banking works
   - Hindi examples: "account kaise kholte hain", "late payment pe kitna charge lagta hai"
   - Telugu examples: "account ela open cheyali", "interest rate enti"
   - These are questions ANY customer could ask, not specific to their own account
   - Do NOT classify as general if they mention "my", "mera", "naa", "nenu" — those are personal

3. smalltalk
   - User is saying something completely unrelated to banking
   - Examples: talking about weather, cricket, movies, random conversation, testing the bot
   - Also includes: when the user says hello, hi, how are you — treat as smalltalk to reset
   - Do NOT classify as smalltalk just because the language is Hindi or Telugu
   - Only smalltalk if the topic itself is not banking related

4. escalate
   - User wants to DO something that requires human intervention
   - Examples: change address, update mobile number, close account, dispute a transaction, modify loan terms, request a new card, make a complaint
   - Hindi examples: "mera address change karna hai", "mujhe complaint karni hai"
   - Telugu examples: "naa address marchali", "complaint cheyali"
   - Also escalate if the user sounds very frustrated or angry
   - Do NOT escalate just because the question is complex — if it is informational route to general

5. exit
   - User clearly wants to END the conversation with nothing more to ask
   - Examples: "bye", "goodbye", "that's all", "no more questions", "thank you that's it", "I'm done"
   - Hindi: "bas ho gaya", "dhanyawad", "theek hai band karo"
   - Telugu: "ante idi chalu", "sari bye", "inkem ledu"
   - IMPORTANT: "thank you" alone is NOT exit — the user might be thanking before asking next question
   - Only exit if they clearly signal the conversation is over
   - "thank you that's all" IS exit. "thank you, what about my EMI" is NOT exit.

Edge cases you must handle correctly:
- Very short inputs like "yes", "no", "okay", "haan", "ledu" — these are follow-up responses, classify based on conversation context
- Partial sentences like "i want to know" — not enough info, classify as smalltalk with low confidence
- Completely unclear or noise-only transcription — classify as smalltalk with confidence 0.0
- User asking about another bank — classify as general, the bot will handle it
- User asking something personal but without saying "my" explicitly — still classify as personal based on context
- Mixed language mid-sentence is normal and expected — classify on meaning

Reply with ONLY valid JSON in this exact format, nothing else, no explanation, no extra text:
{"intent": "personal", "confidence": 0.85}

Confidence guide:
- 0.9 to 1.0 — very clear, no doubt
- 0.7 to 0.9 — fairly clear, minor ambiguity
- below 0.7 — unclear, let the else branch handle it
"""

CONFIDENCE_THRESHOLD = 0.7
# i set this to 0.7 meaning LLM needs to be at least 70% sure
# i use >= not > so exactly 0.7 also counts as confident enough

MAX_INTENT_RETRIES = 3
# this is my safety limit for how many times the personal flow
# can bounce back here without successfully getting a valid customer id
# once this limit hits i stop the loop and escalate to a human


async def classify_intent(chat_history):
    history_text = "\n".join(f"{m['role']}: {m['content']}" for m in chat_history)
    # i flatten the full conversation history into one text block
    # each line is "role: content" so the LLM reads the whole conversation
    # and classifies intent based on full context not just the last message

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
    # i chose smalltalk with 0.0 confidence as fallback
    # 0.0 is below my threshold so it falls into the
    # "not sure, could you repeat" branch which is the safest response

    fallback = {"intent": "smalltalk", "confidence": 0.0}
    return safe_parse_json(raw, fallback)


async def run_intent(conversation_history, text, retry_count=0):
    # retry_count is passed through from personal.py when the user
    # fails to provide a valid customer id and bounces back here
    # i check it against MAX_INTENT_RETRIES to stop infinite loops

    conversation_history.append({"role": "user", "content": text})
    # i add the user text to history before classifying
    # so the LLM sees the full conversation including this latest message

    await speak("Let me check that for you.")
    # i speak immediately so the user hears something while i make the API call
    # prevents awkward silence

    classify_stop  = asyncio.Event()
    classify_timer = asyncio.create_task(run_timer("finding your intent", classify_stop))

    result = await classify_intent(conversation_history)
    # i pass the full conversation history so the classifier
    # understands follow-up questions correctly

    classify_stop.set()
    await classify_timer

    intent     = result.get("intent",     "smalltalk")
    confidence = result.get("confidence", 0.0)
    # i use .get() with defaults not result["intent"]
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
            # i return "exit" because after escalation
            # there is no point continuing to listen

        from handlers.personal import handle_personal
        await handle_personal(conversation_history, retry_count=retry_count)

    elif intent == "general" and confidence >= CONFIDENCE_THRESHOLD:
        from handlers.general import handle_general
        await handle_general(conversation_history, text)
        # i import inside the if block not at the top of the file
        # this is lazy importing — knowledge_base only loads
        # if a general question actually comes in during this call
        # if the user only asks personal questions, general never loads

    elif intent == "smalltalk" and confidence >= CONFIDENCE_THRESHOLD:
        from handlers.smalltalk import handle_smalltalk
        await handle_smalltalk(conversation_history)
        # smalltalk clears history and reintroduces the bot
        # so the next question starts completely fresh

    elif intent == "escalate" and confidence >= CONFIDENCE_THRESHOLD:
        from handlers.escalate import handle_escalate
        await handle_escalate(conversation_history, text)
        return "exit"
        # after raising a ticket the call ends
        # staff takes over from here so i stop listening

    else:
        await speak("I'm not sure I understood that. Could you please repeat or rephrase?")
        # this catches anything below the confidence threshold
        # the while loop in main() continues naturally after this
        # so the bot goes back to listening automatically


async def main():
    conversation_history = [
        {"role": "assistant", "content": "Hello, welcome to XYZ Bank. I am your bank assistant. Ask me anything about your account."}
    ]
    # i seed the history with the opening message
    # so the LLM always knows how the conversation started
    # even on the very first classification call

    await greet()
    # greet() speaks the welcome message out loud
    # i await it so mic only opens after the bot finishes talking

    while True:
        text = await listen()
        # i wait here until the user speaks and goes silent
        # listen() returns the full transcribed sentence as a plain string

        if not text:
            break
        # if listen() returned empty string it means the 20 second silence
        # timeout fired in vachana.py and the session ended
        # i break instead of continue so the program exits cleanly

        result = await run_intent(conversation_history, text)
        # run_intent classifies and routes to the right handler
        # it returns "exit" if the call should end, None otherwise

        if result == "exit":
            break
        # if i got "exit" back i break the while loop
        # which ends the program cleanly


if __name__ == "__main__":
    asyncio.run(main())
    # asyncio.run() starts the event loop and runs main() inside it
    # everything async in this project runs inside this one event loop
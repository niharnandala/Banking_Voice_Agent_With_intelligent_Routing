#langgraph-version

from langgraph.graph import StateGraph, START, END
import sys
import os
import time
from utils.prompt_loader import load_prompt
import asyncio
from typing import TypedDict



sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# fixed: this used to append .../llm_intent_dir/handlers (the handlers folder
# itself) to sys.path, but "from handlers.personal import ..." below needs
# the PARENT of handlers/ on the path, not handlers/ itself
# this only "worked" before because the project root was already on sys.path
# some other way (e.g. running "python app.py" from that folder) — if this
# file is ever imported from a different working directory, the old line
# would not have helped at all
# now this appends the actual project root (this file's own directory),
# which is what "handlers.personal" style imports actually need

from connections.connections import groq_client
from utils.utils import safe_parse_json



class State(TypedDict):
    history:str
    waiting_for:str
    handler:str
    intent:str
    confidence:float
    language:str
    classified_this_turn:bool




llm_intent_prompt = """
You are an intent classifier for an Indian banking voice assistant.

Classify the customer's latest request into exactly one intent, AND detect the
language of the customer's latest message.

Return ONLY valid JSON.

Format:
{"intent":"personal","confidence":0.95,"language":"english"}

Do not explain.
Do not return markdown.
Do not return extra text.

Available intents:
- personal
- general
- escalate
- smalltalk
- exit

Choose exactly one.

Priority (highest first):
1. exit
2. personal
3. general
4. escalate
5. smalltalk

PERSONAL

Choose "personal" ONLY if the latest request can be answered using the customer's personal banking data.

Supported personal data includes ONLY:

Customer
- name
- phone number
- email

Account
- account type
- balance
- minimum balance required
- account status

Loan
- loan type
- principal amount
- outstanding amount
- EMI amount
- EMI due date
- loan status

If the requested information is not listed above, do NOT choose personal.

GENERAL

Choose "general" ONLY if the latest request can be answered using the bank's general policies that apply to every customer.

Examples include:
- account types
- minimum balance rules
- interest rates
- EMI policies
- loan policies
- debit card policies
- credit card policies
- fixed deposits
- internet banking
- mobile banking
- fund transfers
- UPI
- IMPS
- NEFT
- RTGS
- KYC
- complaints

If the answer is not covered by these policies, do NOT choose general.

ESCALATE

Choose "escalate" for any banking request that cannot be answered by either Personal or General.

Also choose "escalate" if the customer:
- wants a human representative
- wants to perform an account action
- is reporting fraud
- is making a complaint
- is abusive or extremely frustrated

SMALLTALK

Greetings, thanks, casual conversation, or anything unrelated to banking.

EXIT

Choose "exit" only if the customer clearly wants to end the conversation.

LANGUAGE DETECTION

The conversation you are given is a sequence of "role: content" lines. Look ONLY at
the most recent "user:" line to detect language — ignore the language used in
earlier turns, since the customer can switch language between turns.

The customer always types using English letters (Roman script), but that does NOT
mean they are speaking English. They may be speaking actual English, or speaking
Hindi or Telugu typed using English letters instead of their native script, or
mixing Hindi and English words in the same sentence.

Classify based ONLY on which actual words appear in the sentence — NOT on how
natural, fluent, or grammatically correct the sentence sounds. Indian English
speakers often phrase things in unusual or non-standard ways ("correct bank
balance in my account", "kindly do the needful") — this is still English if
every word used is an English word. Do not treat awkward phrasing, unusual word
order, or missing grammar as a signal that the sentence is secretly Hindi or
Telugu. Only classify as "hindi" or "hinglish" if actual Hindi words are
present, typed in Roman letters (like "mera", "kya", "chahiye", "batao", "hai").
Only classify as "telugu" if actual Telugu words are present, typed in Roman
letters (like "naaku", "cheppu", "kavali", "enti", "vundi").

Classify the language of the latest customer message into exactly one of:
- "english"    → every word in the sentence is an English word, regardless of
  how the sentence is phrased or structured
- "hindi"      → the sentence is Hindi, just typed in English letters
- "hinglish"   → the sentence mixes actual Hindi words and actual English words
  together
- "telugu"     → the sentence is Telugu, just typed in English letters

There is no dedicated mixed category for Telugu+English the way there is for
Hindi+English. If a sentence mixes Telugu and English words, classify it as
"telugu" if most of the meaningful content words are Telugu, otherwise
classify it as "english".

Examples:
"what is my account balance" → english
"correct bank balance in my account" → english
"kindly do the needful and check my balance" → english
"mera account balance kya hai" → hindi
"please check karke batao mera balance" → hinglish
"mujhe debit card chahiye" → hindi
"can you check mera balance please" → hinglish
"naaku na account balance cheppandi" → telugu
"nenu debit card kavali" → telugu

Ignore language when deciding intent — classify intent purely on meaning.
Only use language for the separate "language" field.

Confidence

Be conservative.

If you are not reasonably certain, return confidence below 0.70.

Never inflate confidence.

"""


CONFIDENCE_THRESHOLD = 0.7
# i set this to 0.7 meaning LLM needs to be at least 70% sure
# i use >= not > so exactly 0.7 also counts as confident enough

MAX_RETRIES = 3
# i stop the personal id loop after 3 failed attempts
# and escalate to a human instead of looping forever

MAX_SMALLTALK = 3
# i stop greeting the user after 3 consecutive smalltalk messages
# and escalate — something is clearly wrong if they keep sending unrelated messages


async def classify_intent(chat_history):
    history_text = "\n".join(f"{m['role']}: {m['content']}" for m in chat_history)
    print(history_text)
    # fixed: this used to be print({history_text}) which wraps the string in
    # a set literal and prints a messy one-item set repr instead of the
    # plain text — this just prints it cleanly now

    start = time.time()
    try:
        response = await asyncio.to_thread( 
            groq_client.chat.completions.create,
                model    = "openai/gpt-oss-120b",
                # swapped from llama-3.1-8b-instant to a bigger model here
                # the 8b model kept misreading unusual-but-fully-English phrasing
                # as Hindi typed in Roman letters, and also adding Telugu detection
                # on top needs more reasoning depth than an 8b model reliably has
                # gpt-oss-120b is also not on Groq's deprecation list, unlike
                # llama-3.1-8b-instant which is being shut down mid-August 2026
                messages = [
                    {"role": "system", "content": llm_intent_prompt},
                    {"role": "user",   "content": history_text}
                ]
        )
        raw = response.choices[0].message.content

    except Exception as e:
        print(f"[error] classify_intent LLM call failed: {e}")
        return {"intent": "smalltalk", "confidence": 0.0, "language": "english"}
    # i chose smalltalk with 0.0 confidence as fallback
    # 0.0 is below my threshold so it falls into the
    # "not sure, could you repeat" branch which is the safest response
    # language defaults to english here too since there's nothing to detect
    # language from if the LLM call itself failed

    print(f"[timing] intent classification: {time.time() - start:.2f}s")

    fallback = {"intent": "smalltalk", "confidence": 0.0, "language": "english"}
    return safe_parse_json(raw, fallback)




async def run_intent(conversation, text):

    history = conversation["history"]
    state   = conversation["state"]
    # i pull these out once at the top so i dont keep writing
    # conversation["history"] and conversation["state"] everywhere below

    history.append({"role": "user", "content": text})
    # i add the user message to history immediately
    # this way every handler and every LLM call sees the full conversation
    # including what the user just said

    if state["waiting_for"] is not None:
        # i always check this before calling the intent LLM
        # if another handler is already waiting for input
        # there is no reason to spend another LLM call deciding intent again
        # i just send the message straight to whoever was waiting
        # note: state["language"] is NOT re-detected on this branch — it stays
        # whatever it was the last time classify_intent actually ran for this
        # personal request, before the id back-and-forth started. that's
        # intentional: we want to answer in the language of the customer's
        # actual question, not whatever language the id-reading-out-loud
        # turn happened to be in

        if state["handler"] == "personal":
            if "last_intent" in conversation:
                conversation["last_intent"]["classified_this_turn"] = False
                # no fresh classify_intent call happens on this branch (that's
                # the whole point of "waiting_for"), so the metrics panel
                # shouldn't present the previous turn's numbers as if they're
                # new — this just flags them as carried over from before
            from handlers.personal import handle_personal
            return await handle_personal(conversation)

        # i can add more waiting handlers here as the project grows
        # eg if state["handler"] == "escalate": ...

    # nobody is waiting for anything
    # this is a fresh new request so i classify the intent

    print("[intent] classifying...")

    _classify_start = time.time()
    result     = await classify_intent(history)
    _classify_time  = time.time() - _classify_start
    intent     = result.get("intent",     "smalltalk")
    confidence = result.get("confidence", 0.0)
    language   = result.get("language",   "english")
    # i use .get() with defaults not result["intent"]
    # because if the key is missing .get() gives me the default
    # and result["intent"] would throw a KeyError and crash

    state["language"] = language
    # every fresh classification saves the detected language onto state
    # this is what personal.py and general.py now read instead of each
    # running their own separate language-detection prompt rule

    conversation.setdefault("timings", []).append({
        "label"   : "intent_classification",
        "seconds" : round(_classify_time, 3)
    })
    conversation["last_intent"] = {
        "intent"               : intent,
        "confidence"           : confidence,
        "language"             : language,
        "classified_this_turn" : True
    }
    # additive bookkeeping only, for a frontend metrics panel — nothing
    # about the routing logic below reads or depends on these two lines.
    # app.py reads conversation["timings"] and conversation["last_intent"]
    # after run_intent returns and attaches them to the /chat response

    print(f"[intent] {intent}, confidence: {confidence}, language: {language}\n")

    if intent == "exit" and confidence >= CONFIDENCE_THRESHOLD:
        # i check exit first before everything else
        # returning this dict signals app.py to clean up the session
        state["smalltalk_count"] = 0
        return {"response": "exit"}

    elif intent == "personal" and confidence >= CONFIDENCE_THRESHOLD:
        state["smalltalk_count"] = 0
        # i reset smalltalk counter whenever a real banking question comes in

        if state["retry_count"] >= MAX_RETRIES:
            # user has failed to give a valid id too many times
            # i reset everything and escalate to a human
            state["retry_count"] = 0
            state["handler"]     = None
            state["waiting_for"] = None
            from handlers.escalate import handle_escalate
            return await handle_escalate(conversation, text)

        from handlers.personal import handle_personal
        return await handle_personal(conversation)

    elif intent == "general" and confidence >= CONFIDENCE_THRESHOLD:
        state["smalltalk_count"] = 0
        from handlers.general import handle_general
        return await handle_general(conversation, text)
        # i import inside the if block not at the top of the file
        # this is lazy importing — knowledge_base only loads
        # if a general question actually comes in during this call

    elif intent == "smalltalk" and confidence >= CONFIDENCE_THRESHOLD:
        from handlers.smalltalk import handle_smalltalk
        return await handle_smalltalk(conversation)
        # i used to bump state["smalltalk_count"] right here AND handle_smalltalk
        # bumped it again on its own — that meant MAX_SMALLTALK = 3 was actually
        # escalating after only 2 real smalltalk turns, not 3
        # now handle_smalltalk owns the counter completely, this just calls it

    elif intent == "escalate" and confidence >= CONFIDENCE_THRESHOLD:
        state["smalltalk_count"] = 0
        from handlers.escalate import handle_escalate
        return await handle_escalate(conversation, text)

    else:
        # this catches anything below the confidence threshold
        # the app just shows this message and waits for the next input
        state["smalltalk_count"] = 0
        return {
            "response": "I'm not sure I understood that. Could you please repeat or rephrase?"
        }




    def classify_intent_node(state:State):
    result = classify_intent(history)

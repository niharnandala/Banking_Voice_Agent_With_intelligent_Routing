import sys
import os
import time
from utils.prompt_loader import load_prompt
import asyncio
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# this appends the project root, this file's own directory, onto sys.path
# handlers.personal style imports below need the parent of handlers/ on
# the path, not handlers/ itself

from connections.connections import groq_client
from utils.utils import safe_parse_json


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
# the classifier needs to be at least 70% sure before i trust its intent
# i use >= not > so exactly 0.7 also counts as confident enough

MAX_RETRIES = 3
# i stop the personal id loop after 3 failed attempts
# and escalate to a human instead of looping forever

MAX_SMALLTALK = 3
# i stop greeting the user after 3 consecutive smalltalk messages
# and escalate, something is clearly wrong if they keep sending unrelated messages


classifier_llm = ChatGroq(
    model   = "openai/gpt-oss-120b",
    api_key = groq_client.api_key
)
# this is the langchain wrapper around the same groq model and the same
# key connections.py already loads for groq_client, i just hand it to
# ChatGroq instead of calling the raw sdk client directly for this one call
# the sdk client itself stays untouched so personal.py and general.py keep
# working exactly as they already do


class ConversationState(TypedDict):
    history      : list
    state        : dict
    text         : str
    timings      : list
    last_intent  : dict
    last_active  : float
    response     : Optional[dict]
    intent       : Optional[str]
    confidence   : Optional[float]
# this is the shape of the same conversation dict app.py already stores
# per session, i am not introducing a second parallel state, the graph
# just operates directly on it
# intent and confidence are scratch fields the classify node fills in and
# the router right after it reads, nothing downstream needs them once
# routing is decided


async def classify_intent(chat_history):
    history_text = "\n".join(f"{m['role']}: {m['content']}" for m in chat_history)
    print(history_text)

    start = time.time()
    try:
        response = await classifier_llm.ainvoke([
            SystemMessage(content=llm_intent_prompt),
            HumanMessage(content=history_text)
        ])
        raw = response.content

    except Exception as e:
        print(f"[error] classify_intent LLM call failed: {e}")
        return {"intent": "smalltalk", "confidence": 0.0, "language": "english"}
    # smalltalk with 0.0 confidence is the fallback here
    # 0.0 sits below the threshold so this falls into the uncertain branch
    # which is the safest response when the classifier itself is unreachable

    print(f"[timing] intent classification: {time.time() - start:.2f}s")

    fallback = {"intent": "smalltalk", "confidence": 0.0, "language": "english"}
    return safe_parse_json(raw, fallback)


async def check_waiting_node(conversation: ConversationState) -> ConversationState:
    return conversation
# this node does no work on its own, it exists purely so the graph has a
# real entry point to hang the waiting/classify branch off of, the actual
# decision happens in route_from_waiting right below


def route_from_waiting(conversation: ConversationState) -> str:
    state = conversation["state"]

    if state["waiting_for"] is not None:
        # another handler is already waiting on the customer's next reply
        # there is no reason to spend an llm call deciding intent again
        # the message goes straight to whoever asked for it

        if state["handler"] == "personal":
            if "last_intent" in conversation:
                conversation["last_intent"]["classified_this_turn"] = False
                # no fresh classify_intent call happens on this branch, so
                # the metrics panel should not present the previous turn's
                # numbers as if they are new, this flags them as carried over
            return "personal"

        # more waiting handlers slot in here as the project grows
        # eg if state["handler"] == "escalate": return "escalate"

    return "classify"


async def classify_node(conversation: ConversationState) -> ConversationState:
    print("[intent] classifying...")

    history = conversation["history"]

    start      = time.time()
    result     = await classify_intent(history)
    elapsed    = time.time() - start
    intent     = result.get("intent",     "smalltalk")
    confidence = result.get("confidence", 0.0)
    language   = result.get("language",   "english")
    # .get() with defaults means a missing key falls back safely instead
    # of throwing a KeyError

    conversation["state"]["language"] = language
    # every fresh classification saves the detected language onto state
    # this is what personal.py and general.py read instead of running
    # their own separate language detection

    conversation.setdefault("timings", []).append({
        "label"   : "intent_classification",
        "seconds" : round(elapsed, 3)
    })
    conversation["last_intent"] = {
        "intent"               : intent,
        "confidence"           : confidence,
        "language"             : language,
        "classified_this_turn" : True
    }
    # bookkeeping only, for the frontend metrics panel, app.py reads
    # conversation["timings"] and conversation["last_intent"] after
    # run_intent returns and attaches them to the /chat response

    conversation["intent"]     = intent
    conversation["confidence"] = confidence
    # scratch fields the router right after this node reads, nothing
    # downstream of routing needs them again

    print(f"[intent] {intent}, confidence: {confidence}, language: {language}\n")
    return conversation


def route_after_classify(conversation: ConversationState) -> str:
    state      = conversation["state"]
    intent     = conversation.get("intent")
    confidence = conversation.get("confidence", 0.0)

    if intent == "exit" and confidence >= CONFIDENCE_THRESHOLD:
        # exit gets checked first, before everything else
        return "exit"

    if intent == "personal" and confidence >= CONFIDENCE_THRESHOLD:
        state["smalltalk_count"] = 0
        # a real banking question resets the smalltalk counter

        if state["retry_count"] >= MAX_RETRIES:
            # the customer already failed to give a valid id too many
            # times, everything resets and this goes to a human instead
            state["retry_count"] = 0
            state["handler"]     = None
            state["waiting_for"] = None
            return "escalate"

        return "personal"

    if intent == "general" and confidence >= CONFIDENCE_THRESHOLD:
        state["smalltalk_count"] = 0
        return "general"

    if intent == "smalltalk" and confidence >= CONFIDENCE_THRESHOLD:
        return "smalltalk"

    if intent == "escalate" and confidence >= CONFIDENCE_THRESHOLD:
        state["smalltalk_count"] = 0
        return "escalate"

    # anything below the confidence threshold lands here
    state["smalltalk_count"] = 0
    return "uncertain"


async def personal_node(conversation: ConversationState) -> ConversationState:
    from handlers.personal import handle_personal
    conversation["response"] = await handle_personal(conversation)
    return conversation


async def general_node(conversation: ConversationState) -> ConversationState:
    from handlers.general import handle_general
    conversation["response"] = await handle_general(conversation, conversation["text"])
    return conversation
    # imported inside the node, not at the top of the file, this is lazy
    # importing, knowledge_base only loads if a general question actually
    # comes in during this call


async def smalltalk_node(conversation: ConversationState) -> ConversationState:
    from handlers.smalltalk import handle_smalltalk
    conversation["response"] = await handle_smalltalk(conversation)
    return conversation


async def escalate_node(conversation: ConversationState) -> ConversationState:
    from handlers.escalate import handle_escalate
    conversation["response"] = await handle_escalate(conversation, conversation["text"])
    return conversation


async def exit_node(conversation: ConversationState) -> ConversationState:
    conversation["state"]["smalltalk_count"] = 0
    conversation["response"] = {"response": "exit"}
    # this exact return value signals app.py to clean up and close the session
    return conversation


async def uncertain_node(conversation: ConversationState) -> ConversationState:
    conversation["response"] = {
        "response": "I'm not sure I understood that. Could you please repeat or rephrase?"
    }
    return conversation


graph = StateGraph(ConversationState)

graph.add_node("check_waiting", check_waiting_node)
graph.add_node("classify",      classify_node)
graph.add_node("personal",      personal_node)
graph.add_node("general",       general_node)
graph.add_node("smalltalk",     smalltalk_node)
graph.add_node("escalate",      escalate_node)
graph.add_node("exit",          exit_node)
graph.add_node("uncertain",     uncertain_node)

graph.add_edge(START, "check_waiting")

graph.add_conditional_edges(
    "check_waiting",
    route_from_waiting,
    {
        "personal" : "personal",
        "classify" : "classify"
    }
)

graph.add_conditional_edges(
    "classify",
    route_after_classify,
    {
        "exit"      : "exit",
        "personal"  : "personal",
        "general"   : "general",
        "smalltalk" : "smalltalk",
        "escalate"  : "escalate",
        "uncertain" : "uncertain"
    }
)

graph.add_edge("personal",  END)
graph.add_edge("general",   END)
graph.add_edge("smalltalk", END)
graph.add_edge("escalate",  END)
graph.add_edge("exit",      END)
graph.add_edge("uncertain", END)

intent_graph = graph.compile()


async def run_intent(conversation, text):
    conversation["text"] = text
    conversation["history"].append({"role": "user", "content": text})
    conversation.setdefault("timings", [])
    # pre-seed timings on the real object before the graph runs — langgraph
    # mutates existing lists in place fine, but a list created fresh
    # inside classify_node would not reach this object

    final_state = await intent_graph.ainvoke(conversation)

    if "last_intent" in final_state:
        conversation["last_intent"] = final_state["last_intent"]
        # last_intent gets reassigned wholesale in classify_node, not
        # mutated in place, so this copies it back explicitly

    return final_state.get("response")
# i do NOT import run_intent here at the top level
# because llm_intent.py imports smalltalk.py
# if i also import llm_intent.py here at the top Python gets stuck
# in a circular import loop and crashes — so i import inside the function

from llm_intent import MAX_SMALLTALK
# importing just the constant is safe even at top level though —
# by the time llm_intent.py lazily imports handle_smalltalk (inside a
# function, not at module load time), llm_intent.py itself has already
# finished loading, so this constant is already sitting there ready
# i moved this here instead of hardcoding MAX_SMALLTALK = 3 twice
# so the two files can never quietly drift apart on this number


async def handle_smalltalk(conversation):

    history = conversation["history"]
    state   = conversation["state"]
    # i pull these out once at the top so i dont keep writing
    # conversation["history"] and conversation["state"] everywhere below

    state["smalltalk_count"] = state.get("smalltalk_count", 0) + 1
    # this file is now the ONLY place that increments smalltalk_count
    # run_intent used to bump it too before calling handle_smalltalk
    # which meant the counter jumped by 2 per smalltalk turn instead of 1
    # and MAX_SMALLTALK = 3 was actually firing after just 2 real turns

    if state["smalltalk_count"] >= MAX_SMALLTALK:
        # user has sent unrelated messages too many times in a row
        # something is wrong — escalate to a human instead of looping
        state["smalltalk_count"] = 0
        print(f"[smalltalk] max smalltalk hits reached — escalating")
        from handlers.escalate import handle_escalate
        return await handle_escalate(conversation, "repeated unrelated messages — possible confused user")

    history.clear()
    # i clear the full history because the user said something unrelated
    # no point carrying old context forward — fresh start is cleaner

    state["handler"]     = None
    state["waiting_for"] = None
    state["retry_count"] = 0
    # i reset the full state too
    # otherwise if we were mid personal flow and smalltalk fired
    # the next message would wrongly route back to personal handler

    greeting = "Hello, I am your XYZ Bank assistant. How can I help you today?"

    history.append({
        "role"    : "assistant",
        "content" : greeting
    })
    # i add the greeting to history so the LLM knows how this fresh
    # conversation started when it classifies the very next intent

    return {
        "response": greeting
    }
    # i return the greeting as text
    # FastAPI sends this to the app which handles TTS
    # this does NOT call listen() or speak() — that is the app's job
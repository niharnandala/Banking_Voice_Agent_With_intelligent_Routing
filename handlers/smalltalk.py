from vachana import speak, listen
# i import speak and listen from vachana for voice in and out
# i do NOT import run_intent here at the top level
# because llm_intent.py imports smalltalk.py at the top
# if i also import llm_intent.py here at the top Python gets stuck
# in a circular import loop and crashes — so i import inside the function


async def handle_smalltalk(conversation_history):

    conversation_history.clear()
    # i clear the full history here because the user said something
    # unrelated to banking — there is no point carrying old context forward
    # starting fresh gives the LLM a clean slate for the next question

    await speak("Hello, I am your XYZ Bank assistant. How can I help you today?")
    # i reintroduce the bot as if it is a brand new call
    # this feels natural to the user instead of the bot just going silent

    conversation_history.append({
        "role"    : "assistant",
        "content" : "Hello, I am your XYZ Bank assistant. How can I help you today?"
    })
    # i add the greeting to history so the LLM knows how this fresh
    # conversation started when it classifies the next intent

    user_text = await listen()
    # i listen for what the user actually wants after the reset
    # this is their real question now that the bot has reintroduced itself

    from llm_intent import run_intent
    # i import here inside the function not at the top of the file
    # this avoids the circular import problem explained above
    await run_intent(conversation_history, user_text)
    # i send the new question back into the normal routing flow
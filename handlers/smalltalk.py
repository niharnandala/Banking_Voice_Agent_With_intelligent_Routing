# handlers/smalltalk.py


from vachana import speak, listen


async def handle_smalltalk(conversation_history):

    conversation_history.clear()

    await speak("Hello, I am your XYZ Bank assistant. How can I help you today?")

    conversation_history.append({
        "role"    : "assistant",
        "content" : "Hello, I am your XYZ Bank assistant. How can I help you today?"
    })

    user_text = await listen()

    # imported here, not at top -- prevents circular import
    # llm_intent imports smalltalk, so smalltalk cannot import llm_intent at top level
    from llm_intent import run_intent
    await run_intent(conversation_history, user_text)
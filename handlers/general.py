import re
import asyncio
from vachana import speak, run_timer
from connections import groq_client
from knowledge_base import search_knowledge_base
# i imported search_knowledge_base at the top level here
# this means knowledge_base.py gets imported once when this file first loads
# the embedding model loads at that moment and stays in memory
# every subsequent call to handle_general reuses the already loaded model
# Python caches module imports so it never reloads


general_prompt = """
You are a banking voice assistant. Answer the customer's question
using ONLY the information provided below from our knowledge base.

Knowledge base information:
{chunks}

Rules:
- Reply in plain spoken sentences only
- No bullet points, no bold, no markdown formatting of any kind
- Keep it short, like you are speaking out loud to someone on a phone call
- Do not make up anything not present in the information above
- If the information above does not answer the question, say you will connect them to a staff member
- At the end of the answer ask whether they have any other questions
"""
# i wrote these rules for the same reason as personal.py
# spoken responses need to be clean plain sentences
# {chunks} gets replaced with the actual retrieved text when i call .format()


def clean_for_speech(text):
    # exact same cleaning function as personal.py
    # i strip markdown, bullet points, and extra whitespace
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'^\s*[-•]\s*', '', text, flags=re.MULTILINE)
    text = ' '.join(text.split())
    return text


def format_chunks(chunks):
    # my search returns a list of chunk dictionaries
    # each one has a "text" key with the actual policy content
    # i join them all with double newlines so the LLM sees them
    # as separate paragraphs rather than one long smashed together string
    return "\n\n".join(c["text"] for c in chunks)


async def handle_general(conversation_history, user_text):

    await speak("Let me look that up for you.")
    # i speak immediately so the user knows something is happening
    # the knowledge base search and LLM call take a few seconds
    # without this the user would sit in silence wondering if the bot died

    search_stop  = asyncio.Event()
    search_timer = asyncio.create_task(run_timer("searching knowledge base", search_stop))

    try:
        chunks = search_knowledge_base(user_text)
        # i pass the user's raw question directly to the search function
        # it converts the question to a vector embedding and finds
        # the most semantically similar chunks from ChromaDB
    except Exception as e:
        print(f"[error] knowledge base search failed: {e}")
        search_stop.set()
        await search_timer
        await speak("I'm having trouble searching for that right now. Let me connect you to a staff member.")
        from handlers.escalate import handle_escalate
        await handle_escalate(conversation_history, user_text)
        return
    # if ChromaDB is down or the embedding model fails
    # i catch it here and escalate instead of crashing

    search_stop.set()
    await search_timer

    if not chunks:
        # the search ran fine but found nothing relevant
        # this means the user asked something outside the knowledge base
        # i tell them honestly and connect them to a human
        await speak("I'm sorry, I don't have information on that. Let me connect you to a staff member.")
        from handlers.escalate import handle_escalate
        await handle_escalate(conversation_history, user_text)
        return

    chunk_text = format_chunks(chunks)
    # i format all the retrieved chunks into one clean text block
    # this goes into the system prompt so the LLM answers from it

    answer_stop  = asyncio.Event()
    answer_timer = asyncio.create_task(run_timer("fetching your answer", answer_stop))

    try:
        response = groq_client.chat.completions.create(
            model    = "llama-3.1-8b-instant",
            messages = [
                {"role": "system", "content": general_prompt.format(chunks=chunk_text)},
                # i bake the retrieved chunks into the system prompt
                # the LLM can only answer from what i give it here
                *conversation_history,
                # full conversation history so the LLM has context
                {"role": "user", "content": user_text}
                # user's actual question goes last
            ]
        )
        raw_reply = response.choices[0].message.content

    except Exception as e:
        print(f"[error] general answer LLM call failed: {e}")
        answer_stop.set()
        await answer_timer
        await speak("I'm having trouble getting your answer right now. Please try again in a moment.")
        return
    # if Groq is down i stop the timer cleanly and
    # tell the user to try again instead of crashing

    answer_stop.set()
    await answer_timer

    clean_reply = clean_for_speech(raw_reply)
    conversation_history.append({"role": "assistant", "content": raw_reply})
    print(f"\nbot: {clean_reply}\n")
    await speak(clean_reply)
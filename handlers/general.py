import sys
import os

import re
from vachana import speak,run_timer
from connections import groq_client
from knowledge_base import search_knowledge_base
import asyncio

general_prompt="""
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
- After Answering the question completely ,ask if they had any other questions.
"""

def clean_for_speech(text):
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'^\s*[-•]\s*', '', text, flags=re.MULTILINE)
    text = ' '.join(text.split())
    return text

def format_chunks(chunks):
    return "\n\n".join(c["text"] for c in chunks)


async def handle_general(conversation_history,user_text):
    # speak immediately so user knows something is happening
    await speak("Let me look that up for you.")

    search_stop=asyncio.Event()
    search_timer=asyncio.create_task(run_timer("searching for knowledge base",search_stop))

    chunks=search_knowledge_base(user_text)
    search_stop.set()
    if not chunks:
        await speak("I'm sorry, I don't have information on that. Let me connect you to a staff member.")
        from handlers.escalate import handle_escalate
        await handle_escalate(conversation_history, user_text)


        return
    
    chunk_text = format_chunks(chunks)

    answer_stop=asyncio.Event()
    answer_timer = asyncio.create_task(run_timer("fetching your answer", answer_stop))
    response = groq_client.chat.completions.create(
        model    = "llama-3.1-8b-instant",
        messages = [
            # system: rules + knowledge base chunks
            {"role": "system", "content": general_prompt.format(chunks=chunk_text)},

            # middle: conversation history so LLM knows context
            *conversation_history,

            # last: what the user actually asked
            {"role": "user", "content": user_text}
        ]
    )

    answer_stop.set()
    await answer_timer

    # step 4: extract, clean, speak
    raw_reply   = response.choices[0].message.content
    clean_reply = clean_for_speech(raw_reply)

    conversation_history.append({"role": "assistant", "content": raw_reply})
    print(f"\nbot: {clean_reply}\n")
    await speak(clean_reply)


    

import asyncio
from vachana import start_listening
from connections import groq_client

prompt = """
You are an intent classifier for a banking voice agent.
Classify the user query into exactly one of these:
- general: bank policies, EMI policies, how to open account, public info
- personal: balance, EMI due date, loan amount, personal account data
- smalltalk: greetings, rubbish, not related to banking at all
- escalate: modifying something, complex request, needs staff help

Reply in this exact format:
intent: <one word>
confidence: <number between 0.0 and 1.0>
"""

async def handle(text):
    response = groq_client.chat.completions.create(
        model    = "llama-3.1-8b-instant",
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user",   "content": text}
        ]
    )
    result = response.choices[0].message.content.strip()
    print(f"\n{result}\n")

asyncio.run(start_listening(handle, listen_once=True))
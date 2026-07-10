import asyncio
from vachana_stt.vachana import listen, speak, run_timer
from connections.connections import groq_client
from scripts.queries import get_customer_full_data, validate_customer_id
from utils.utils import clean_for_speech, safe_parse_json


id_prompt = """
You are helping extract a customer ID from what a banking customer just said over a phone call.

Customer IDs follow this exact pattern: the letters CU followed by exactly 3 digits.
Valid examples: CU001, CU045, CU123.
Invalid examples: CU0001, CU12, CU1234, CU00.

IMPORTANT — people speak their ID in many broken ways over phone calls due to speech-to-text errors:
- "c u zero zero one" means CU001
- "it is c u 001" means CU001
- "see you double o one" means CU001
- "cu 45" means CU045 — pad with leading zero
- "c u zero four five" means CU045
- "my id is see you one two three" means CU123
- "customer id cu001" means CU001

Be flexible. Extract the ID even if spacing, capitalization, or spelled-out numbers are used.
If you can reasonably tell what the customer ID is meant to be, extract it in standard format CUxxx.
If the customer said something completely unrelated to giving an ID, return has_id false.

Reply with ONLY valid JSON. No explanation, no extra text, nothing else:
{{"has_id": true, "customer_id": "CU001"}}
or
{{"has_id": false, "customer_id": null}}

User said: {text}
"""
# this prompt handles the reality of speech to text on phone calls
# people never say CU001 cleanly — they spell it out, break it up, say zero instead of O
# instead of writing regex for every variation we just teach the LLM the pattern with examples
# double curly braces bcuzz .format() is called on this string — single braces would crash


data_answer_prompt = """
You are a friendly frontline call centre agent for XYZ Bank.
You speak exactly like a trained agent at HDFC or ICICI phone banking — warm, helpful, natural.
You support Hindi, English, Telugu, and Hinglish. Always respond in the SAME language the customer is speaking.
If they speak Hindi, reply in Hindi. If Telugu, reply in Telugu. If Hinglish, reply in Hinglish. Never force English.

Customer data available to you:
{data}

How you must behave:

LANGUAGE AND TONE:
- Match the customer's language exactly
- Be warm and friendly, not stiff or corporate
- Use "sir" or "ma'am" naturally, only where it fits — not after every sentence
- Speak like you are on a phone call — short sentences, natural flow
- Never use bullet points, bold text, asterisks, or markdown of any kind — this is a voice call

ANSWERING:
- Always confirm what you found before answering, like "I can see your account here sir"
- Say amounts with "rupees" — "25,000 rupees" not just "25,000"
- Use natural phrases like "as per our records" or "I can see here" only when they genuinely fit, not in every sentence
- Never make up data not present in the customer data above
- If something is not in the data say: "I don't have that detail handy right now, but our branch team can help you with that"
- After answering, always ask: "Is there anything else I can help you with today?"

EDGE CASES YOU MUST HANDLE:
- If customer is angry or frustrated: acknowledge first, stay calm, do not argue — "I completely understand sir, let me help you right away"
- If customer asks same question twice: answer again politely, never say "as I mentioned"
- If STT gave you a garbled or incomplete sentence: ask to repeat — "I'm sorry, I didn't quite catch that, could you say that again please?"
- If customer asks something outside your data: be honest, do not guess, offer to connect to branch
- If customer says thank you or goodbye: close warmly — "Thank you for calling XYZ Bank, have a wonderful day sir"
- If customer mixes languages mid-sentence: match their mix naturally, do not switch back to full English

WHAT YOU MUST NEVER DO:
- Never say "I am an AI" or "I am a bot"
- Never use "certainly", "absolutely", "of course" — these sound fake and robotic
- Never repeat the customer's full question back to them before answering
- Never give a disclaimer about being unable to access real systems
- Never end without asking if they need anything else

Current conversation so far:
{history}

Customer just said: {question}

Respond now as the call centre agent. Keep it natural, keep it short, speak like a real person on a phone call.
"""
# this prompt is written to sound like a real indian bank call centre agent not a generic llm
# the never do list is critical bcuzz llms default to "certainly" and "of course" constantly
# matching the customer language is what makes this feel natural not robotic
# {data}, {history}, {question} all get replaced when we call .format() later


async def handle_personal(conversation_history, retry_count=0):
    # retry_count tracks how many times we looped here without a valid customer id
    # prevents infinite loop between personal.py and llm_intent.py
    # after 3 failed attempts we stop and send to a human

    MAX_RETRIES = 3
    if retry_count >= MAX_RETRIES:
        await speak("I'm having trouble getting your details. Let me connect you to one of our staff members who can assist you better.")
        from handlers.escalate import handle_escalate
        await handle_escalate(conversation_history, "")
        return

    # step 1 — check if customer already gave their id in conversation history
    # no need to ask again if they already mentioned it earlier in the call
    history_text = "\n".join(f"{m['role']}: {m['content']}" for m in conversation_history)

    pre_check_stop  = asyncio.Event()
    pre_check_timer = asyncio.create_task(run_timer("checking conversation history", pre_check_stop))

    try:
        pre_check_response = groq_client.chat.completions.create(
            model    = "llama-3.1-8b-instant",
            messages = [
                {"role": "system", "content": id_prompt.format(text=history_text)},
                {"role": "user",   "content": history_text}
            ]
        )
        pre_check = safe_parse_json(
            pre_check_response.choices[0].message.content,
            {"has_id": False, "customer_id": None}
        )
    except Exception:
        pre_check = {"has_id": False, "customer_id": None}

    pre_check_stop.set()
    await pre_check_timer

    if pre_check.get("has_id"):
        # customer already mentioned their id earlier in the conversation
        # skip asking and go straight to fetching their data
        customer_id = pre_check.get("customer_id")
        print(f"\ncustomer id found in history: {customer_id}\n")

    else:
        # customer id not found in history — ask for it now
        await speak("Please tell me your customer ID.")
        conversation_history.append({"role": "assistant", "content": "asked for customer id"})

        user_text = await listen()
        # listen() opens mic, waits for user to finish speaking, returns text
        conversation_history.append({"role": "user", "content": user_text})

        await speak("One moment please.")

        check_stop  = asyncio.Event()
        check_timer = asyncio.create_task(run_timer("checking your id", check_stop))

        try:
            id_response = groq_client.chat.completions.create(
                model    = "llama-3.1-8b-instant",
                messages = [
                    {"role": "system", "content": id_prompt.format(text=user_text)},
                    {"role": "user",   "content": user_text}
                ]
            )
            raw_id_result = id_response.choices[0].message.content
            # choices[0] is first completion, .message.content is the plain text reply

        except Exception as e:
            print(f"[error] id extraction LLM call failed: {e}")
            check_stop.set()
            await check_timer
            await speak("I'm having some trouble right now. Let me connect you to a staff member.")
            from handlers.escalate import handle_escalate
            await handle_escalate(conversation_history, user_text)
            return

        check_stop.set()
        await check_timer

        fallback  = {"has_id": False, "customer_id": None}
        id_result = safe_parse_json(raw_id_result, fallback)
        # safe_parse_json finds the first {...} in the reply and parses it
        # if llm returned extra text around json this handles it safely

        if not id_result.get("has_id"):
            # user said something unrelated instead of giving their id
            # send back to run_intent to re-classify what they actually want
            from llm_intent import run_intent
            # importing here not at top to avoid circular import
            # llm_intent imports personal at top level
            # if personal also imported llm_intent at top level python would crash with import loop
            await run_intent(conversation_history, user_text, retry_count=retry_count + 1)
            return

        customer_id = id_result.get("customer_id")
        print(f"\ncustomer_id: {customer_id}\n")

    # step 2 — validate that this customer id actually exists in database
    # llm sometimes extracts ids that look valid but dont exist in our records
    if not validate_customer_id(customer_id):
        await speak("I could not find an account with that ID. Could you please tell me your customer ID again?")
        await handle_personal(conversation_history, retry_count=retry_count + 1)
        # calling myself again with retry bumped by 1
        return

    await speak("Thank you, got it.")
    conversation_history.append({"role": "assistant", "content": f"got customer id: {customer_id}"})

    # step 3 — fetch full customer data from database
    try:
        data = get_customer_full_data(customer_id)
    except Exception as e:
        print(f"[error] get_customer_full_data failed: {e}")
        await speak("I'm having trouble fetching your details right now. Let me connect you to a staff member.")
        from handlers.escalate import handle_escalate
        await handle_escalate(conversation_history, "")
        return

    if data is None:
        # rare case — id validated but full fetch returned nothing
        # could happen if database is in a weird state
        await speak("I'm having trouble fetching your details right now. Let me connect you to a staff member.")
        from handlers.escalate import handle_escalate
        await handle_escalate(conversation_history, "")
        return

    # step 4 — find the original question customer asked before we started the id flow
    # we look backwards through history to find what they actually wanted
    original_question = ""
    for msg in reversed(conversation_history):
        if msg["role"] == "user" and "customer id" not in msg["content"].lower():
            original_question = msg["content"]
            break

    # step 5 — send original question + customer data to llm to generate a natural answer
    answer_stop  = asyncio.Event()
    answer_timer = asyncio.create_task(run_timer("fetching your answer", answer_stop))

    try:
        answer_response = groq_client.chat.completions.create(
            model    = "llama-3.1-8b-instant",
            messages = [
                {"role": "system", "content": data_answer_prompt.format(
                    data     = data,
                    history  = history_text,
                    question = original_question
                )},
                # we bake customer data and full history into system prompt
                # llm can only answer from what we give it here — no hallucination possible
                {"role": "user", "content": original_question}
            ]
        )
        raw_reply = answer_response.choices[0].message.content

    except Exception as e:
        print(f"[error] answer LLM call failed: {e}")
        answer_stop.set()
        await answer_timer
        await speak("I'm having trouble getting your answer right now. Please try again in a moment.")
        return

    answer_stop.set()
    await answer_timer

    clean_reply = clean_for_speech(raw_reply)
    # strips any markdown llm added — asterisks, hashes, bullet dashes
    # these sound terrible when spoken out loud

    conversation_history.append({"role": "assistant", "content": raw_reply})
    # we store raw reply in history not cleaned version
    # bcuzz llm reads history and understands markdown
    # only the spoken version needs cleaning

    print(f"\nbot: {clean_reply}\n")
    await speak(clean_reply)

    # step 6 — listen for follow up question
    # the prompt always closes with "is there anything else"
    # so we listen again and route whatever they say next back through intent classification
    follow_up_text = await listen()
    if follow_up_text:
        conversation_history.append({"role": "user", "content": follow_up_text})
        from llm_intent import run_intent
        await run_intent(conversation_history, follow_up_text)
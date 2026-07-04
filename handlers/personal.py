import asyncio
from vachana import listen, speak, run_timer
from connections import groq_client
from queries import get_customer_full_data, validate_customer_id
from utils import clean_for_speech, safe_parse_json
# i import clean_for_speech and safe_parse_json from utils.py
# instead of defining them here — one place to maintain them


id_prompt = """
We are currently expecting the user to provide their customer id.
Customer ids follow the pattern CU followed by exactly 3 digits, like CU001, CU002, CU045.

People often say this out loud in broken or spelled out ways due to speech-to-text errors, for example:
- "it is c u 001" means CU001
- "c u zero zero one" means CU001
- "cu 045" means CU045
- "see you double o one" means CU001

Be flexible and extract the id even if spacing, capitalization, or spelled-out numbers are used.
The id must be exactly CU followed by exactly 3 digits. CU0001 or CU1234 are NOT valid.
If you can reasonably tell what the customer id is meant to be, extract it in the standard format CUxxx.

Reply with ONLY valid JSON in this exact format, nothing else:
{{"has_id": true, "customer_id": "CU001"}}
or
{{"has_id": false, "customer_id": null}}

User said: {text}
"""
# i wrote this prompt to handle messy speech to text reality
# people dont say CU001 cleanly, they say "see you zero zero one"
# instead of writing regex for every variation i just tell the LLM
# what the pattern is and give examples — it handles the rest
# double curly braces {{}} because .format() is called on this string later
# single braces would be treated as format placeholders and crash


data_answer_prompt = """
You are a professional banking voice assistant speaking exactly like a trained Indian private bank call centre agent, similar to HDFC or ICICI phone banking staff.

Customer data:
{data}

How you must speak:
- Address the customer respectfully as "sir" or "ma'am" naturally within sentences but make it sound natural and use it where its only needed
- Always say amounts with "rupees" after the number, for example "25,000 rupees" not just "25,000"
- Use phrases like "as per our records", "I would like to inform you", "kindly note that" whenever it is required
- Confirm what you found before answering, like "I can see your account here sir"
- Be warm but professional — not too casual, not too stiff
- Keep sentences short and spoken naturally, like you are on a phone call but do not over talk unneccesarly
- Never use bullet points, bold, markdown, or lists of any kind
- Do not make up anything not present in the customer data above
- If a detail is not in the data, say "I'm afraid I don't have that information handy sir, but our branch team will be able to assist you with that"
- After fully answering, always close with: "Is there anything else I can assist you with today sir" or "ma'am" depending on context

Example of how you should sound:
"Thank you for your patience sir. As per our records, your current account balance is 25,000 rupees. Kindly note that this reflects your available balance as of today. Is there anything else I can assist you with today sir?"
"""
# i wrote these rules because LLMs naturally format with bold and bullets
# which sounds terrible when spoken — "asterisk asterisk balance asterisk asterisk"
# {data} gets replaced with the actual customer data when i call .format(data=data)


async def handle_personal(conversation_history, retry_count=0):
    # retry_count tracks how many times we bounced here without a valid id
    # once it hits MAX_INTENT_RETRIES in llm_intent.py we escalate to human
    # this prevents infinite loop between personal.py and llm_intent.py

    # step 1: ask the user for their customer id
    await speak("Please tell me your customer id.")
    # i await speak because it blocks until the bot finishes talking
    # only then does the mic open — prevents bot hearing itself
    conversation_history.append({"role": "assistant", "content": "please tell your customer id"})

    # step 2: listen to what the user says
    user_text = await listen()
    # listen() opens mic, waits for speech and silence, returns transcribed text
    conversation_history.append({"role": "user", "content": user_text})

    # step 3: send to LLM to extract the customer id
    check_stop  = asyncio.Event()
    check_timer = asyncio.create_task(run_timer("checking your id", check_stop))
    # i start a timer task alongside the LLM call
    # it prints elapsed time in terminal so i can see how long it takes
    # i stop it after the LLM call finishes

    try:
        id_response = groq_client.chat.completions.create(
            model    = "llama-3.1-8b-instant",
            messages = [
                {"role": "system", "content": id_prompt.format(text=user_text)},
                {"role": "user",   "content": user_text}
            ]
        )
        # i send the prompt with the user's words baked in
        # the LLM reads the rules and extracts the id in CUxxx format
        raw_id_result = id_response.choices[0].message.content
        # choices[0] is the first completion, .message.content is the plain text

    except Exception as e:
        # if Groq is down or API call fails i catch it here
        print(f"[error] id extraction LLM call failed: {e}")
        check_stop.set()
        await check_timer
        await speak("I'm having some trouble right now. Let me connect you to a staff member.")
        from handlers.escalate import handle_escalate
        await handle_escalate(conversation_history, user_text)
        return
        # i stop the timer first then escalate to human

    check_stop.set()
    await check_timer

    # step 4: parse the LLM reply safely
    fallback  = {"has_id": False, "customer_id": None}
    id_result = safe_parse_json(raw_id_result, fallback)
    # if parsing fails i get has_id False which sends user back to try again

    if id_result.get("has_id"):
        # i use .get() not id_result["has_id"] because if key is missing
        # .get() returns None safely instead of crashing with KeyError

        customer_id = id_result.get("customer_id")
        print(f"\ncustomer_id: {customer_id}\n")

        if not validate_customer_id(customer_id):
            # LLM extracted something that looks like a valid id
            # but i confirm it actually exists in my database
            # if not i tell the user and ask them to try again
            await speak(f"I could not find any account with ID {customer_id}. Could you please tell me your customer ID again?")
            await handle_personal(conversation_history, retry_count=retry_count + 1)
            # i call myself again with retry_count bumped by 1
            return

        await speak("Thank you, got it.")
        conversation_history.append({"role": "assistant", "content": f"got customer id: {customer_id}"})

        # step 5: fetch the customer's real data from the database
        try:
            data = get_customer_full_data(customer_id)
        except Exception as e:
            print(f"[error] get_customer_full_data failed: {e}")
            await speak("I'm having trouble fetching your details right now. Let me connect you to a staff member.")
            from handlers.escalate import handle_escalate
            await handle_escalate(conversation_history, user_text)
            return
        # i wrap the DB call in try/except because the DB could go down
        # between the validate call above and this call

        if data is None:
            # rare case — id validated but full fetch returned nothing
            # could happen if DB is in a weird state
            await speak("I'm having trouble fetching your details right now. Let me connect you to a staff member.")
            from handlers.escalate import handle_escalate
            await handle_escalate(conversation_history, user_text)
            return

        # step 6: send question + customer data to LLM to generate answer
        answer_stop  = asyncio.Event()
        answer_timer = asyncio.create_task(run_timer("fetching your answer", answer_stop))

        try:
            answer_response = groq_client.chat.completions.create(
                model    = "llama-3.1-8b-instant",
                messages = [
                    {"role": "system", "content": data_answer_prompt.format(data=data)},
                    # i bake customer data into system prompt
                    # LLM can only answer from what i give it here
                    *conversation_history,
                    # full history so LLM has full context
                    {"role": "user", "content": user_text}
                    # user question goes last
                ]
            )
            raw_reply = answer_response.choices[0].message.content

        except Exception as e:
            print(f"[error] answer LLM call failed: {e}")
            answer_stop.set()
            await answer_timer
            await speak("I'm having trouble getting your answer right now. Please try again in a moment.")
            return
        # if LLM fails i stop timer and tell user to try again

        answer_stop.set()
        await answer_timer

        clean_reply = clean_for_speech(raw_reply)
        # i clean the reply to strip any markdown the LLM added

        conversation_history.append({"role": "assistant", "content": raw_reply})
        # i add raw reply to history not cleaned version
        # because LLM reads history and understands markdown
        # only the spoken version needs cleaning

        print(f"\nbot: {clean_reply}\n")
        await speak(clean_reply)

    else:
        # LLM could not extract a customer id from what user said
        # i send back to run_intent to re-classify
        from llm_intent import run_intent
        # i import here not at top to avoid circular import
        # llm_intent.py imports personal.py at top level
        # so personal.py cannot import llm_intent.py at top level
        # Python would get stuck in an import loop and crash
        await run_intent(conversation_history, user_text, retry_count=retry_count + 1)
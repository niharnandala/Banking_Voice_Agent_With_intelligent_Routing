import re
import json
import asyncio
from vachana import listen, speak, run_timer
from connections import groq_client
from queries import get_customer_full_data, validate_customer_id
# i imported re for cleaning markdown from LLM responses
# json for parsing the LLM's JSON output safely
# asyncio for my timers and async operations
# listen and speak from vachana for voice input and output
# run_timer to show live progress in the terminal
# groq_client is my connection to the Groq LLM API
# get_customer_full_data and validate_customer_id are my two DB functions


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
# i wrote this prompt to handle the messy reality of speech to text
# people dont say "CU001" cleanly, they say "see you zero zero one"
# or "c u 001" or all kinds of variations
# instead of writing regex to handle every case, i just tell the LLM
# what the pattern is and give it examples — it handles the rest
# i use double curly braces {{}} because this string goes through
# .format() later and single braces would be treated as format placeholders


data_answer_prompt = """
You are a banking voice assistant. Answer the customer's question
using ONLY the customer data provided below.
- After answering the question completely, ask: do you have any other questions?


Customer data:
{data}

Rules:
- Reply in plain spoken sentences only
- No bullet points, no bold, no markdown formatting of any kind
- Keep it short, like you are speaking out loud to someone on a phone call
- Do not make up anything not present in the customer data above
"""
# i wrote these rules because LLMs naturally want to format their responses
# with bullet points and bold text which sounds terrible when spoken out loud
# "asterisk asterisk your balance is asterisk asterisk" is not what i want
# the {data} placeholder gets replaced with the actual customer data
# when i call .format(data=data) later


def _safe_parse_json(raw_text, fallback):
    # i wrote this helper because LLMs dont always return clean JSON
    # even when i tell them to return ONLY JSON they sometimes wrap it
    # in markdown fences like ```json { } ``` or add a sentence before it
    # instead of crashing every time that happens i handle it here

    cleaned = raw_text.strip()
    # first i strip any leading or trailing whitespace

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    # if the LLM wrapped the JSON in backticks i strip those off
    # then if it starts with the word "json" i remove that too
    # then i strip whitespace again to get the clean JSON string

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[warning] could not parse LLM JSON: {e!r}, raw was: {raw_text!r}")
        return fallback
    # i try to parse the cleaned string as JSON
    # if it fails for any reason i print a warning and return
    # whatever fallback the caller gave me instead of crashing


def clean_for_speech(text):
    # i wrote this as a safety net for cases where the LLM
    # ignores my prompt rules and adds markdown anyway
    text = re.sub(r'\*+', '', text)
    # this removes all asterisks — catches both bold ** and italic *

    text = re.sub(r'^\s*[-•]\s*', '', text, flags=re.MULTILINE)
    # this removes bullet point characters at the start of any line
    # re.MULTILINE makes ^ match start of each line not just start of string

    text = ' '.join(text.split())
    # this collapses all extra whitespace and newlines into single spaces
    # so the spoken output is one clean continuous sentence

    return text


async def handle_personal(conversation_history, retry_count=0):
    # i removed update_status and update_conversation parameters
    # app.py now redirects sys.stdout to StreamlitLogger
    # so every print() here automatically shows in the browser
    # no need to pass streamlit functions through every function anymore

    # retry_count tracks how many times we have bounced through here
    # without successfully getting a valid customer id
    # once it hits MAX_INTENT_RETRIES in llm_intent.py we stop and escalate
    # this prevents the infinite loop between personal and llm_intent

    # step 1: ask the user for their customer id
    await speak("Please tell me your customer id.")
    # i await speak because speak is async — it blocks until the bot
    # actually finishes talking before the mic opens again
    conversation_history.append({"role": "assistant", "content": "please tell your customer id"})
    # i add this to history so the LLM knows what was said at each step

    # step 2: listen to what the user says
    user_text = await listen()
    # listen() opens the mic, waits for the user to speak and go silent,
    # then returns the full transcribed text as a plain string
    conversation_history.append({"role": "user", "content": user_text})

    # step 3: send what they said to the LLM to extract the customer id
    check_stop  = asyncio.Event()
    check_timer = asyncio.create_task(run_timer("checking your id", check_stop))
    # i create a stop event and start a timer task running alongside
    # the timer just prints elapsed time in the terminal so i can see
    # how long the LLM call is taking — i stop it after the call finishes

    try:
        id_response = groq_client.chat.completions.create(
            model    = "llama-3.1-8b-instant",
            messages = [
                {"role": "system", "content": id_prompt.format(text=user_text)},
                {"role": "user",   "content": user_text}
            ]
        )
        # i send the id_prompt with the user's text baked in
        # the LLM reads the prompt rules and the user's words
        # and extracts the customer id in standard CUxxx format
        raw_id_result = id_response.choices[0].message.content
        # i dig into the response object to get the actual text
        # choices[0] is the first (and only) completion
        # .message.content is the plain text string i want

    except Exception as e:
        # if Groq is down or the API call fails for any reason
        # i catch it here so the whole call doesnt crash
        print(f"[error] id extraction LLM call failed: {e}")
        check_stop.set()
        await check_timer
        await speak("I'm having some trouble right now. Let me connect you to a staff member.")
        from handlers.escalate import handle_escalate
        await handle_escalate(conversation_history, user_text)
        return
        # i set the stop event first so the timer prints its final time
        # then i escalate to a human since i cant extract the id

    check_stop.set()
    await check_timer
    # i stop the timer now that the LLM call is done

    # step 4: parse the LLM reply safely
    fallback  = {"has_id": False, "customer_id": None}
    id_result = _safe_parse_json(raw_id_result, fallback)
    # i pass a safe fallback so if parsing fails i get has_id False
    # which sends the user back through the flow to try again

    if id_result.get("has_id"):
        # i use .get() instead of id_result["has_id"] because if the key
        # is missing for any reason .get() returns None instead of crashing

        customer_id = id_result.get("customer_id")
        print(f"\ncustomer_id: {customer_id}\n")

        if not validate_customer_id(customer_id):
            # the LLM extracted something that looks like a valid id
            # but i need to confirm it actually exists in my database
            # if it doesnt i tell the user and ask them to try again
            await speak(f"I could not find any account with ID {customer_id}. Could you please tell me your customer ID again?")
            await handle_personal(conversation_history, retry_count=retry_count + 1)
            # i call myself again with retry_count bumped up by 1
            # llm_intent.py will stop this loop once retries hit the max
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
        # i wrap the DB call in try/except because the database
        # could go down between the validate call and this call
        # if it fails i escalate instead of crashing

        if data is None:
            # this is a rare case — the id validated just above
            # but the full data fetch returned nothing
            # this could happen if the DB is in a weird state
            await speak("I'm having trouble fetching your details right now. Let me connect you to a staff member.")
            from handlers.escalate import handle_escalate
            await handle_escalate(conversation_history, user_text)
            return

        # step 6: send the question + customer data to LLM to generate an answer
        answer_stop  = asyncio.Event()
        answer_timer = asyncio.create_task(run_timer("fetching your answer", answer_stop))

        try:
            answer_response = groq_client.chat.completions.create(
                model    = "llama-3.1-8b-instant",
                messages = [
                    {"role": "system", "content": data_answer_prompt.format(data=data)},
                    # i bake the customer data into the system prompt
                    # so the LLM answers only from this customer's real data
                    *conversation_history,
                    # i spread the full conversation history in the middle
                    # so the LLM knows the full context of what was discussed
                    {"role": "user", "content": user_text}
                    # i put the user's question last so the LLM answers it
                ]
            )
            raw_reply = answer_response.choices[0].message.content

        except Exception as e:
            print(f"[error] answer LLM call failed: {e}")
            answer_stop.set()
            await answer_timer
            await speak("I'm having trouble getting your answer right now. Please try again in a moment.")
            return
        # if the LLM call fails i stop the timer cleanly
        # and tell the user to try again instead of crashing

        answer_stop.set()
        await answer_timer

        clean_reply = clean_for_speech(raw_reply)
        # i run the reply through my cleaning function to strip
        # any markdown the LLM might have added despite my prompt rules

        conversation_history.append({"role": "assistant", "content": raw_reply})
        # i add the raw reply to history not the cleaned one
        # because history is for the LLM to read and the LLM
        # understands markdown — only the spoken version needs cleaning

        print(f"\nbot: {clean_reply}\n")
        await speak(clean_reply)

    else:
        # the LLM could not extract a customer id from what the user said
        # i send the text back to run_intent to re-classify
        # maybe they said something different and the intent changed
        from llm_intent import run_intent
        # i import here not at the top to avoid circular import
        # llm_intent.py imports personal.py at the top
        # so if personal.py also imports llm_intent.py at the top
        # Python gets stuck in an import loop and crashes
        await run_intent(conversation_history, user_text, retry_count=retry_count + 1)
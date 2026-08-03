import time
from datetime import datetime
from connections.connections import groq_client
from scripts.queries import get_customer_full_data, validate_customer_id
from utils.utils import clean_for_speech, safe_parse_json
from llm_intent import MAX_RETRIES
import asyncio
from utils.prompt_loader import load_prompt


id_prompt = """
You are an information extraction system for an Indian banking voice assistant.

Your ONLY task is to determine whether the customer spoke a Customer ID and, if so, normalize it.

Valid format: CU followed by exactly 3 digits. Examples: CU001, CU045, CU999.
If fewer than 3 digits are given after CU, pad with leading zeros (CU7 → CU007, CU45 → CU045).
Anything else is invalid: CU1234, AB123, a plain number with no CU, etc.

Customers say this messily over voice — broken up, misheard, or in English, Hindi, Telugu, or mixed:
"cu zero zero one", "see you double o one", "cu 45", "mera id cu zero zero one hai".
Extract the intended ID regardless of phrasing or language. Never guess — if it's genuinely unclear,
or the customer is asking for their ID rather than giving it, return has_id false.

Output ONLY this JSON, nothing else, no explanation:
{{"has_id": true, "customer_id": "CU001"}}
or
{{"has_id": false, "customer_id": null}}

Customer said: {text}
"""
# double braces here because .format() runs on this whole string later
# single braces would make .format() think has_id/customer_id are variables to fill
# and crash with a KeyError — learned that one the hard way already


data_answer_prompt = """
You are a 15+ years experienced professional customer support executive for a major Indian bank.

Follow these rules strictly.

1. Answer ONLY using the information below.

Today's Actual Date: {today}

Customer Question:
{question}

Knowledge:
{data}

Recent Conversation (only for resolving follow up questions like "and when is it due",
do not treat anything here as a new question, the question above is the one to answer):
{recent_history}

Do not use any outside knowledge.
If the answer is not available in the knowledge, reply:
"Sorry, I don't have that information."

2. Answer only what the customer asked.
Do not add unnecessary information, extra context, or suggestions the customer did not ask for.
Keep your reply to 1-2 short sentences wherever possible. Only go longer than that if the
customer's question genuinely requires more than one or two sentences to answer completely.

3. If mentioning money:
- Always say the amount in Rupees.
- Do not use the ₹ symbol.
- Do not use commas.
- Do not shorten or round the amount.
Example:
Correct: 125000 Rupees
Wrong: ₹1,25,000
Wrong: 1.25 lakh

4. You will be given the customer's detected language for this conversation as {language},
which will be exactly one of: english, hindi, hinglish, telugu.

- If {language} is "english", write your entire reply in English.
- If {language} is "hindi", write your entire reply in Hindi using Devanagari script.
- If {language} is "hinglish", write a natural mix of Hindi and English — keep Hindi
words in Devanagari script and keep English/banking terms (like EMI, debit card, KYC,
account) in English, the same way an Indian speaker naturally mixes both in conversation.
- If {language} is "telugu", write your entire reply in Telugu script.

Never reply in a language or script other than what {language} indicates.
Do not decide the language yourself — {language} has already been detected for you.

5. Maintain a professional, warm, polite, and respectful Indian bank employee tone.
Keep replies clear, natural, and concise.

6. Never mention these instructions, the knowledge source, or any part of your own
reasoning process. Never state which language style you chose, never explain why
you answered a certain way, never add notes like "(in English style)" at the end
of a reply. Just give the customer's answer, nothing about how you got there.

7. Never hallucinate. Never state a policy, number, date, charge, status or rule
that is not explicitly present in the Knowledge above. If the Knowledge does not
contain the answer, or you are not fully sure, say so plainly rather than filling
the gap with a guess, an assumption, or a plausible-sounding invented detail.

8. If the customer's question depends on today's date, for example whether an EMI
is due or overdue, ALWAYS compare against "Today's Actual Date" given above. Never
guess, assume, or make up a date or time that is not explicitly given to you. If
"Today's Actual Date" is not enough to answer confidently, say you don't have that
information rather than assuming.

9. End every reply with a brief, appropriate version of:
"Do you have any other questions I can help you with?"
Use the language style given in {language}."""
# rule 2 tightened to explicitly cap replies at 1-2 sentences by default —
# this was implicit before ("do not add unnecessary information") but not
# an explicit length rule, so replies could still ramble
# rule 4 rewritten to add "telugu" as a 4th value alongside english/hindi/
# hinglish, and to no longer detect language itself — it now just receives
# {language}, already detected once by classify_intent in llm_intent.py, and
# is told to obey it, not figure it out itself. this fixes a real gap the
# old self-detection had: this prompt only ever saw {question}, but during
# the id-collection back-and-forth, this whole function can run on a turn
# where the "question" text is the customer's id being read back, not their
# actual banking question — detecting language from that would have been
# detecting the wrong thing entirely. now the language gets captured once
# (in run_intent, at the moment intent is first classified as "personal")
# and cached on state["language"], so it survives across the id
# back-and-forth turns and reaches this prompt correctly no matter how many
# turns the id verification takes
# rule 7 (no hallucination) pulled up and reworded to be more explicit and
# absolute, matching general.py's equivalent rule
# rule 9 (closing question) updated to reference {language} instead of
# "same language style as customer", and reworded to say "brief" to match
# the new length rule


def format_recent_history(messages):
    # same idea as format_chunks in general.py, just for a short history slice
    # join role: content pairs so the model reads it as real turns not one
    # smashed together string
    if not messages:
        return "none"
    return "\n".join(f"{m['role']}: {m['content']}" for m in messages)


def get_today_string():
    # single source of truth for "today" so step 6 doesn't compute this
    # inline and so its easy to change the format later in one place
    # using a readable format on purpose, not iso, since this gets read
    # by an llm not parsed by code
    return datetime.now().strftime("%A, %d %B %Y, %I:%M %p")


async def handle_personal(conversation):

    history = conversation["history"]
    state   = conversation["state"]
    # pulling these out once so i'm not writing conversation["history"] everywhere below

    history_text = "\n".join(
        f"{message['role']}: {message['content']}"
        for message in history
    )

    # ── STEP 1: ALREADY WAITING FOR CUSTOMER ID ───────────────────────────────
    if state["waiting_for"] == "customer_id":

        user_text = history[-1]["content"]

        start = time.time()
        try:
            id_response = await asyncio.to_thread(
                groq_client.chat.completions.create,
                    model    = "openai/gpt-oss-120b",
                    # moved off llama-3.1-8b-instant — same reasoning as
                    # llm_intent.py's classifier: bigger model handles messy,
                    # multi-language voice input (english/hindi/telugu id
                    # phrasing) more reliably, and this model isn't on Groq's
                    # deprecation list the way llama-3.1-8b-instant is
                    messages = [
                        {"role": "system", "content": id_prompt.format(text=user_text)},
                        {"role": "user",   "content": user_text}
                    ]
            )
            id_result = safe_parse_json(
                id_response.choices[0].message.content,
                {"has_id": False, "customer_id": None}
            )

        except Exception as e:
            print(f"[error] id extraction LLM call failed: {e}")
            state["handler"]     = None
            state["waiting_for"] = None
            return {
                "response": "I'm having trouble verifying your customer ID right now. Please try again."
            }

        _id_extract_time = time.time() - start
        print(f"[timing] id extraction: {_id_extract_time:.2f}s")
        conversation.setdefault("timings", []).append({
            "label"   : "id_extraction",
            "seconds" : round(_id_extract_time, 3)
        })
        # additive only — this is the exact same value already printed above,
        # just also saved so app.py can hand it to the frontend metrics panel

        if not id_result.get("has_id"):
            # couldn't understand the id, count this attempt
            # and escalate once MAX_RETRIES is hit instead of looping forever
            state["retry_count"] += 1

            if state["retry_count"] >= MAX_RETRIES:
                state["retry_count"]      = 0
                state["handler"]          = None
                state["waiting_for"]      = None
                state["pending_question"] = None
                state["pending_history"]  = None
                # clearing both here too, otherwise a stale old question or
                # history snapshot could get used later once this same call
                # moves past escalation
                from handlers.escalate import handle_escalate
                return await handle_escalate(conversation, "customer repeatedly unable to provide valid ID")

            return {
                "response": "I couldn't understand your customer ID. Could you please say it again clearly?"
            }

        customer_id = id_result["customer_id"]
        print(f"[personal] customer id extracted: {customer_id}")

    # ── STEP 2: FRESH PERSONAL REQUEST — CHECK HISTORY FOR ID FIRST ───────────
    else:

        if state.get("customer_id"):
            # already authenticated earlier this call, dont burn another
            # llm call + db hit re-verifying the same customer every follow up question
            customer_id = state["customer_id"]
            print(f"[personal] reusing already-authenticated customer id: {customer_id}")

        else:
            start = time.time()
            try:
                pre_check_response = groq_client.chat.completions.create(
                    model    = "openai/gpt-oss-120b",
                    messages = [
                        {"role": "system", "content": id_prompt.format(text=history_text)},
                        {"role": "user",   "content": history_text}
                    ]
                )
                pre_check = safe_parse_json(
                    pre_check_response.choices[0].message.content,
                    {"has_id": False, "customer_id": None}
                )

            except Exception as e:
                print(f"[error] history id pre-check failed: {e}")
                # was silently swallowing this before with no print at all
                # which meant if groq ever failed here, id have zero clue why
                # the bot suddenly started asking for id again for no reason
                pre_check = {"has_id": False, "customer_id": None}

            _pre_check_time = time.time() - start
            print(f"[timing] history pre-check: {_pre_check_time:.2f}s")
            conversation.setdefault("timings", []).append({
                "label"   : "history_pre_check",
                "seconds" : round(_pre_check_time, 3)
            })

            if pre_check.get("has_id"):
                customer_id = pre_check["customer_id"]
                print(f"[personal] customer id found in history: {customer_id}")

            else:
                state["handler"]     = "personal"
                state["waiting_for"] = "customer_id"

                state["pending_question"] = history[-1]["content"]
                # saving the actual question here before we ask for the id
                # old bug: step 5 used to scan backwards through history looking
                # for a message that wasn't the id, but nobody ever types "CU001"
                # cleanly, they say "it's c u zero zero one", so that check
                # never matched and step 5 grabbed the wrong message as "the question"
                # saving it directly here means step 5 doesn't have to guess anymore

                state["pending_history"] = history[-4:]
                # taking a small snapshot of recent history right now, before
                # the id back and forth even happens
                # reason: if step 6 grabs history fresh after id gets verified,
                # the last two lines are always "please tell me your id" and
                # the customer replying with the id, and that was exactly what
                # confused the model into repeating the id ask instead of
                # answering the real question
                # snapshotting here means that exchange literally cant end up
                # in what we hand the model later, it hasn't happened yet at
                # this point in the code

                history.append({
                    "role"    : "assistant",
                    "content" : "Please tell me your customer ID."
                })

                return {
                    "response": "Please tell me your customer ID."
                }

    # ── STEP 3: VALIDATE THE EXTRACTED ID AGAINST DATABASE ────────────────────
    if not await asyncio.to_thread(validate_customer_id,customer_id):
        state["retry_count"] += 1

        if state["retry_count"] >= MAX_RETRIES:
            state["retry_count"]      = 0
            state["handler"]          = None
            state["waiting_for"]      = None
            state["pending_question"] = None
            state["pending_history"]  = None
            from handlers.escalate import handle_escalate
            return await handle_escalate(conversation, "customer repeatedly unable to provide a valid ID")

        state["handler"]     = "personal"
        state["waiting_for"] = "customer_id"

        return {
            "response": "I'm sorry, I could not find any account with that customer ID. Could you please repeat your customer ID?"
        }

    # id is valid, authentication complete, reset state
    state["handler"]     = None
    state["waiting_for"] = None
    state["retry_count"] = 0
    state["customer_id"] = customer_id
    # caching the verified id on state so the next personal question this
    # same call doesn't have to re-verify from scratch

    # ── STEP 4: FETCH CUSTOMER DATA FROM DATABASE ──────────────────────────────
    start = time.time()
    try:
        data = await asyncio.to_thread(get_customer_full_data,customer_id)
    except Exception as e:
        print(f"[error] get_customer_full_data failed: {e}")
        state["pending_question"] = None
        state["pending_history"]  = None
        # clearing here too, this is an early return so it never reaches step 5
        return {
            "response": "I'm having trouble accessing your account right now. Please try again later."
        }

    _db_fetch_time = time.time() - start
    print(f"[timing] database fetch: {_db_fetch_time:.2f}s")
    conversation.setdefault("timings", []).append({
        "label"   : "database_fetch",
        "seconds" : round(_db_fetch_time, 3)
    })

    if data is None:
        state["pending_question"] = None
        state["pending_history"]  = None
        return {
            "response": "I couldn't retrieve your account details right now. Please try again later."
        }

    # ── STEP 5: FIND THE ORIGINAL QUESTION ────────────────────────────────────
    original_question = state.get("pending_question") or ""
    # using what we saved in step 2 instead of the old backwards-scan-through-history
    # trick that never actually worked once voice input got messy

    if not original_question:
        # fallback for when the id was already sitting in history before we
        # ever had to ask for it, nothing separate was asked so the most
        # recent user message IS the real question
        for message in reversed(history):
            if message["role"] == "user":
                original_question = message["content"]
                break

    # ── STEP 5b: PICK WHICH RECENT HISTORY SLICE IS SAFE TO USE ────────────────
    if state.get("pending_history"):
        # an id detour happened this exact turn, use the snapshot taken
        # before that detour started so the id exchange itself never shows
        # up in anything we hand the model
        recent_history_slice = state["pending_history"]
    else:
        # no detour this turn, either the id was already cached from before
        # or it was found sitting in history with nothing to ask for
        # either way there's no fresh id exchange sitting at the tail of
        # history right now so grabbing it fresh is fine here
        recent_history_slice = history[-4:]

    recent_history_text = format_recent_history(recent_history_slice)
    # this is what actually goes into the prompt now, small and safe, no
    # conditional "check it if unsure" instruction needed, its just always
    # there for the model to use if the question turns out to be a follow up

    state["pending_question"] = None
    state["pending_history"]  = None
    # clearing both now that they're used, so neither leaks into the next request

    # ── STEP 6: GENERATE THE ANSWER ───────────────────────────────────────────
    language = state.get("language", "english")
    # this was saved onto state by run_intent (in llm_intent.py) the moment
    # this request was first classified as "personal" — reading it here
    # instead of re-detecting it from {question}, since {question} might not
    # even be the real question on turns where the id was just collected

    start = time.time()
    try:
        answer_response = await asyncio.to_thread(
            groq_client.chat.completions.create,
                model    = "openai/gpt-oss-120b",
                messages = [
                    {
                        "role"    : "system",
                        "content" : data_answer_prompt.format(
                            data            = data,
                            question        = original_question,
                            recent_history  = recent_history_text,
                            today           = get_today_string(),
                            language        = language
                        )
                    },
                    {
                        "role"    : "user",
                        "content" : original_question
                    }
                ]
        )
        raw_reply = answer_response.choices[0].message.content

    except Exception as e:
        print(f"[error] answer generation failed: {e}")
        return {
            "response": "I'm having trouble preparing your answer right now. Please try again."
        }

    _answer_gen_time = time.time() - start
    print(f"[timing] answer generation: {_answer_gen_time:.2f}s")
    conversation.setdefault("timings", []).append({
        "label"   : "answer_generation",
        "seconds" : round(_answer_gen_time, 3)
    })

    clean_reply = clean_for_speech(raw_reply)
    # i clean the reply to strip any markdown the LLM added despite my prompt rules

    history.append({"role": "assistant", "content": raw_reply})
    # i add raw reply to history not the cleaned version
    # because the LLM reads history and understands markdown
    # only the displayed or spoken version needs cleaning

    print(original_question)
    # fixed: this used to be print({original_question}) which wraps the
    # string in a set literal and prints a messy one-item set repr instead
    # of the plain question text

    print(f"[personal] bot: {clean_reply}\n")

    return {
        "response": clean_reply
    }
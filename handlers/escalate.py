import uuid
import datetime
# i import uuid to generate a unique ticket id for each escalation
# i import datetime to timestamp exactly when the ticket was raised
# no vachana import here — escalate returns text, app handles delivery


async def handle_escalate(conversation, text):

    history = conversation["history"]
    state   = conversation["state"]
    # i pull these out once at the top so i dont keep writing
    # conversation["history"] and conversation["state"] everywhere

    ticket = {
        "ticket_id" : str(uuid.uuid4())[:8].upper(),
        # uuid4() generates a random unique id every time
        # i take only the first 8 characters to keep it short
        # .upper() makes it look cleaner like A3F9B2C1

        "time"      : datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        # i format the timestamp as a readable string

        "issue"     : text,
        # i store exactly what the user said so staff knows the issue

        "summary"   : _summarize_history(history)
        # i include a short summary of the last few conversation turns
        # so staff has full context when they pick up the ticket
    }

    print("\n" + "=" * 50)
    print("ESCALATION TICKET RAISED")
    print("=" * 50)
    print(f"  ticket id  : {ticket['ticket_id']}")
    print(f"  time       : {ticket['time']}")
    print(f"  issue      : {ticket['issue']}")
    print(f"  summary    : {ticket['summary']}")
    print("=" * 50 + "\n")
    # i print the full ticket to the terminal so staff can see it
    # in production this would write to a database or ticketing system

    history.append({
        "role"    : "assistant",
        "content" : f"escalation ticket raised: {ticket['ticket_id']}"
    })
    # i add the ticket to history so there is a record in the conversation

    return {
        "response" : f"I have raised a ticket for you sir. Your ticket ID is {ticket['ticket_id']}. A staff member will contact you shortly.",
        "ticket"   : ticket
        # i return the full ticket object too
        # so the app can store it, display it, or forward it to staff systems
    }


def _summarize_history(conversation_history):
    # i take the last 4 messages from the conversation
    # this gives staff enough context without overwhelming them
    last_turns = conversation_history[-4:]
    return " | ".join(f"{m['role']}: {m['content']}" for m in last_turns)
    # i join each turn with a pipe separator
    # so the summary reads like "user: ... | assistant: ... | user: ..."
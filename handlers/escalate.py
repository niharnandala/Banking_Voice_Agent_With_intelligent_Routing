import uuid
import datetime
from vachana import speak
# i import uuid to generate a unique ticket id for each escalation
# datetime to timestamp when the ticket was raised
# speak to tell the customer their ticket id out loud


async def handle_escalate(conversation_history, user_text):

    ticket = {
        "ticket_id" : str(uuid.uuid4())[:8].upper(),
        # uuid4() generates a random unique id every time
        # i take only the first 8 characters to keep it short
        # .upper() makes it look cleaner like A3F9B2C1

        "time"      : datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        # i format the timestamp as a readable string
        # strftime lets me control the exact format

        "issue"     : user_text,
        # i store exactly what the user said so staff knows the issue

        "summary"   : _summarize_history(conversation_history)
        # i include a short summary of the conversation
        # so staff has full context when they pick up the ticket
    }

    # i print the ticket in the terminal so staff can see it
    print("\n" + "=" * 50)
    print("ESCALATION TICKET RAISED")
    print("=" * 50)
    print(f"  ticket id  : {ticket['ticket_id']}")
    print(f"  time       : {ticket['time']}")
    print(f"  issue      : {ticket['issue']}")
    print(f"  summary    : {ticket['summary']}")
    print("=" * 50 + "\n")

    await speak(f"I have raised a ticket for you. Your ticket id is {ticket['ticket_id']}. A staff member will contact you shortly.")
    # i read the ticket id out loud so the customer has a reference number


def _summarize_history(conversation_history):
    # i take the last 4 messages from the conversation
    # this gives staff enough context without overwhelming them
    last_turns = conversation_history[-4:]
    return " | ".join(f"{m['role']}: {m['content']}" for m in last_turns)
    # i join each turn with a pipe separator
    # so the summary reads like "user: ... | assistant: ... | user: ..."
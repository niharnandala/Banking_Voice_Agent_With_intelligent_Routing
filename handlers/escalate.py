import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid
import datetime
from vachana import speak


async def handle_escalate(conversation_history, user_text):

    # build a simple ticket
    ticket = {
        "ticket_id"  : str(uuid.uuid4())[:8].upper(),   # short random id eg A3F9B2C1
        "time"       : datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "issue"      : user_text,
        "summary"    : _summarize_history(conversation_history)
    }

    # print ticket so staff can see it
    print("\n" + "=" * 50)
    print("ESCALATION TICKET RAISED")
    print("=" * 50)
    print(f"  ticket id  : {ticket['ticket_id']}")
    print(f"  time       : {ticket['time']}")
    print(f"  issue      : {ticket['issue']}")
    print(f"  summary    : {ticket['summary']}")
    print("=" * 50 + "\n")

    # tell the customer
    await speak(f"I have raised a ticket for you. Your ticket id is {ticket['ticket_id']}. A staff member will contact you shortly.")


def _summarize_history(conversation_history):
    # just join the last few turns so staff knows the context
    last_turns = conversation_history[-4:]   # last 4 messages is enough
    return " | ".join(f"{m['role']}: {m['content']}" for m in last_turns)
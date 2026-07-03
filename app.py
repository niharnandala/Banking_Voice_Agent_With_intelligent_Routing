import nest_asyncio
nest_asyncio.apply()
# i need this because streamlit runs its own event loop internally
# and asyncio.run() would normally crash saying "event loop already running"
# nest_asyncio patches this so both loops can coexist

import sys
import asyncio
import streamlit as st
from llm_intent import main


# ── STREAMLIT LOGGER ───────────────────────────────────────────────────────────

class StreamlitLogger:
    # i wrote this to redirect every print() in my entire pipeline
    # into a streamlit box instead of the terminal
    # this means vachana.py, llm_intent.py, personal.py, general.py —
    # every single print() shows up in the browser automatically
    # i dont need to pass update_status into every function anymore

    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.logs        = []
        # placeholder is the streamlit empty box i want to write into
        # logs is my running list of lines to display

    def write(self, text):
        if text.strip():
            # i only add non-empty lines — ignore blank prints
            self.logs.append(text.strip())
            # i show only the last 30 lines so the box doesnt get too long
            self.placeholder.code("\n".join(self.logs[-30:]))

    def flush(self):
        pass
        # streamlit doesnt need flushing but sys.stdout expects this method
        # so i define it as empty to avoid AttributeError


# ── PAGE LAYOUT ────────────────────────────────────────────────────────────────

st.title("🏦 XYZ Bank Voice Agent")
st.caption("🚧 under development — Vachana TTS, Hindi support, and FastAPI deployment coming soon")

st.divider()

col1, col2 = st.columns([1, 2])
# i split the page into two columns
# left column has the button and status
# right column shows the live pipeline logs

with col1:
    st.subheader("Controls")
    start_button = st.button("🎤 Start Talking", use_container_width=True)
    status_text  = st.empty()
    # status_text shows a simple one-line status above the log box

with col2:
    st.subheader("Live Pipeline")
    log_box = st.empty()
    # log_box is where all my terminal output will appear live


# ── START ──────────────────────────────────────────────────────────────────────

if start_button:
    status_text.info("🎤 listening... speak now")

    # i redirect sys.stdout to my StreamlitLogger
    # from this point every print() anywhere in the pipeline
    # goes into log_box instead of the terminal
    sys.stdout = StreamlitLogger(log_box)

    try:
        asyncio.run(main())
    finally:
        # i always restore stdout when done
        # even if the pipeline crashes so the terminal works normally after
        sys.stdout = sys.__stdout__
        status_text.success("✅ call ended")
import re
import json


def clean_for_speech(text):
    # i use this to strip any markdown the LLM adds despite my prompt rules
    # removes bold **, italic *, bullet points, and collapses extra whitespace
    # both personal.py and general.py import this from here
    # so i only have to maintain it in one place
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'^\s*[-•]\s*', '', text, flags=re.MULTILINE)
    text = ' '.join(text.split())
    return text


def safe_parse_json(raw_text, fallback):
    # i use this whenever i parse LLM output because LLMs sometimes
    # wrap JSON in ```json fences or add a sentence before it
    # instead of crashing i strip the wrapping and fall back safely
    # both personal.py and llm_intent.py import this from here
    cleaned = raw_text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[warning] could not parse LLM JSON: {e!r}, raw was: {raw_text!r}")
        return fallback
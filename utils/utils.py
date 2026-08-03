import re
import json
# i import re for cleaning markdown from LLM responses
# i import json for safe parsing of LLM output
# both clean_for_speech and safe_parse_json were previously
# defined separately in personal.py and llm_intent.py
# i moved them here so there is only one place to maintain them



def clean_for_speech(text):
    # i use this to strip any markdown the LLM adds despite my prompt rules
    # removes bold **, italic *, bullet points, and collapses extra whitespace
    # both personal.py and general.py import this from here
    text = re.sub(r'\*+', '', text)
    # this removes all asterisks — catches both ** bold and * italic

    text = re.sub(r'^\s*[-•]\s*', '', text, flags=re.MULTILINE)
    # this removes bullet point characters at the start of any line
    # re.MULTILINE makes ^ match start of each line not just start of string

    text = ' '.join(text.split())
    # this collapses all extra whitespace and newlines into single spaces
    # so the output is one clean continuous sentence

    return text


def safe_parse_json(raw_text, fallback):
    # i use this whenever i parse LLM output
    # because LLMs sometimes wrap JSON in ```json fences
    # or add a sentence before the JSON despite being told not to
    # instead of crashing i strip the wrapping and fall back safely

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
    # if parsing fails for any reason i return the fallback
    # the caller always provides a safe fallback for exactly this situation
    # so nothing crashes
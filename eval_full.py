"""
Unified eval — one test set, every number.

WHAT THIS DOES
--------------
Runs test_set.jsonl through your REAL pipeline pieces (not simulated) and
reports:
  - intent classification accuracy (overall + per intent + confusion)
  - language detection accuracy (overall + per language + confusion)
  - classify_intent() latency: p50 / p95
  - for "personal" cases: real DB fetch (get_customer_full_data) success
    rate + latency p50/p95, using your actual seeded customers
  - for "general" cases: real knowledge-base retrieval accuracy (does the
    top-returned chunk come from the section you labeled as correct) +
    search latency p50/p95
  - "escalation classification rate": of the messages labeled escalate,
    what % the classifier actually sent to escalate

IMPORTANT — what this does NOT measure:
  "Escalation classification rate" above is not the same as your system's
  real-world escalation rate. Real escalation also happens from things a
  single classified message can't show — e.g. a customer failing ID
  verification 3 times, or a genuine general question missing the
  knowledge base. Report this number as exactly what it is: how often the
  classifier correctly routes an escalate-worthy message to escalate.

HOW TO RUN
----------
1. Drop this file and test_set.jsonl into your project root (same folder
   as llm_intent.py, connections/, scripts/, handlers/).
2. Make sure your .env / environment has GROQ_API_KEY, DB_HOST, DB_NAME,
   DB_USER, DB_PASSWORD set — this script hits the real Groq API and the
   real Postgres DB, same as the live app.
3. From the project root:
       python eval_full.py test_set.jsonl
   Optionally pace requests to avoid rate-limit-induced latency spikes
   (see PACING note below):
       python eval_full.py test_set.jsonl --delay 0.5

   Note: importing search_knowledge_base loads the sentence-transformers
   embedding model and connects to ChromaDB — first run will print
   "loading embedding model..." and take a few seconds before the eval
   itself starts. That's expected, same as the app's own startup.

PACING — why this exists
-------------------------
Running 95+ requests back-to-back with zero delay is a burst pattern
that can trip Groq's rate limiting, which shows up as some individual
calls taking 8-12s instead of the normal ~1-2s — NOT because the model
is actually slow, but because requests are queuing/retrying behind the
scenes. That kind of burst also isn't realistic anyway: real callers are
naturally spaced out by conversation, TTS playback, etc. --delay adds a
wait between each test case so the latency numbers you get out reflect
realistic pacing instead of an artificial traffic burst. Default is 0
(no delay, fastest to run) — pass --delay 0.5 (or higher, e.g. 1.0) if
you see wildly inconsistent per-call timings like the ones described
above and want a cleaner latency read.

test_set.jsonl FIELDS
----------------------
Required on every line: "message", "intent", "language"
Optional, only for intent == "personal": "customer_id"
    (must be a real seeded customer id, e.g. CU001 — used to test the
    real DB fetch, not just the classifier)
Optional, only for intent == "general": "expected_section"
    (must exactly match a "section" value from your bank_policies.jsonl,
    e.g. "Interest Rates" — used to test real retrieval accuracy, not
    just the classifier)
"""

import sys
import json
import asyncio
import time
import csv
import argparse
from collections import defaultdict

from llm_intent import classify_intent
from scripts.queries import get_customer_full_data
from scripts.knowledge_base import search_knowledge_base


GREETING = "Hello, welcome to XYZ Bank. I am your bank assistant. Ask me anything about your account."


def percentile(sorted_vals, pct):
    if not sorted_vals:
        return None
    idx = min(int(len(sorted_vals) * pct), len(sorted_vals) - 1)
    return sorted_vals[idx]


async def run_eval(path, delay=0.0):
    with open(path, "r", encoding="utf-8") as f:
        cases = [json.loads(line) for line in f if line.strip()]

    results = []
    intent_confusion = defaultdict(lambda: defaultdict(int))
    lang_confusion = defaultdict(lambda: defaultdict(int))
    classify_latencies = []
    db_latencies = []
    kb_latencies = []
    db_successes = 0
    db_total = 0
    kb_correct = 0
    kb_total = 0

    for i, case in enumerate(cases):
        if delay > 0 and i > 0:
            await asyncio.sleep(delay)
            # spaces requests out instead of firing all 95 back-to-back —
            # see the PACING note in the module docstring for why this
            # matters for getting an honest latency read

        message = case["message"]
        true_intent = case["intent"]
        true_language = case.get("language")

        history = [
            {"role": "assistant", "content": GREETING},
            {"role": "user", "content": message}
        ]

        # ---- intent + language classification ----
        start = time.time()
        result = await classify_intent(history)
        classify_elapsed = time.time() - start
        classify_latencies.append(classify_elapsed)

        pred_intent = result.get("intent", "?")
        pred_language = result.get("language", "?")
        confidence = result.get("confidence", 0.0)

        intent_correct = pred_intent == true_intent
        lang_correct = (true_language is None) or (pred_language == true_language)

        intent_confusion[true_intent][pred_intent] += 1
        if true_language:
            lang_confusion[true_language][pred_language] += 1

        row = {
            "message": message,
            "true_intent": true_intent,
            "pred_intent": pred_intent,
            "intent_correct": intent_correct,
            "true_language": true_language,
            "pred_language": pred_language,
            "lang_correct": lang_correct,
            "confidence": confidence,
            "classify_seconds": round(classify_elapsed, 3),
            "db_seconds": None,
            "db_success": None,
            "kb_section_correct": None,
            "kb_seconds": None,
        }

        # ---- personal cases: real DB fetch ----
        customer_id = case.get("customer_id")
        if true_intent == "personal" and customer_id:
            db_total += 1
            start = time.time()
            try:
                data = await asyncio.to_thread(get_customer_full_data, customer_id)
                db_ok = data is not None
            except Exception as e:
                print(f"    [db error] {customer_id}: {e}")
                db_ok = False
            db_elapsed = time.time() - start
            db_latencies.append(db_elapsed)
            if db_ok:
                db_successes += 1
            row["db_seconds"] = round(db_elapsed, 3)
            row["db_success"] = db_ok

        # ---- general cases: real KB retrieval accuracy ----
        expected_section = case.get("expected_section")
        if true_intent == "general" and expected_section:
            kb_total += 1
            start = time.time()
            try:
                chunks = await asyncio.to_thread(search_knowledge_base, message)
                top_section = chunks[0]["section"] if chunks else None
                section_correct = top_section == expected_section
            except Exception as e:
                print(f"    [kb error] \"{message[:40]}\": {e}")
                section_correct = False
            kb_elapsed = time.time() - start
            kb_latencies.append(kb_elapsed)
            if section_correct:
                kb_correct += 1
            row["kb_seconds"] = round(kb_elapsed, 3)
            row["kb_section_correct"] = section_correct

        results.append(row)

        status = "OK   " if intent_correct else "WRONG"
        extra = ""
        if row["db_success"] is not None:
            extra = f"  db={'ok' if row['db_success'] else 'FAIL'}"
        if row["kb_section_correct"] is not None:
            extra = f"  kb={'ok' if row['kb_section_correct'] else 'MISS'}"
        print(f"[{i+1}/{len(cases)}] {status}  true={true_intent:10s} pred={pred_intent:10s} "
              f"conf={confidence:.2f}{extra}  \"{message[:45]}\"")

    return {
        "results": results,
        "intent_confusion": intent_confusion,
        "lang_confusion": lang_confusion,
        "classify_latencies": classify_latencies,
        "db_latencies": db_latencies,
        "kb_latencies": kb_latencies,
        "db_successes": db_successes,
        "db_total": db_total,
        "kb_correct": kb_correct,
        "kb_total": kb_total,
    }


def summarize(agg):
    results = agg["results"]
    n = len(results)
    intent_acc = sum(r["intent_correct"] for r in results) / n

    lang_cases = [r for r in results if r["true_language"] is not None]
    lang_acc = (sum(r["lang_correct"] for r in lang_cases) / len(lang_cases)) if lang_cases else None

    cl_sorted = sorted(agg["classify_latencies"])
    db_sorted = sorted(agg["db_latencies"])
    kb_sorted = sorted(agg["kb_latencies"])

    print("\n" + "=" * 65)
    print("SUMMARY")
    print("=" * 65)
    print(f"Total test cases          : {n}")
    print(f"Intent accuracy           : {intent_acc*100:.1f}%")
    if lang_acc is not None:
        print(f"Language accuracy         : {lang_acc*100:.1f}%  (n={len(lang_cases)})")
    print(f"Classification latency    : p50 {percentile(cl_sorted, 0.50):.2f}s   "
          f"p95 {percentile(cl_sorted, 0.95):.2f}s")

    if agg["db_total"] > 0:
        print(f"\nDB fetch success rate     : {agg['db_successes']}/{agg['db_total']} "
              f"({agg['db_successes']/agg['db_total']*100:.1f}%)")
        print(f"DB fetch latency          : p50 {percentile(db_sorted, 0.50):.3f}s   "
              f"p95 {percentile(db_sorted, 0.95):.3f}s")

    if agg["kb_total"] > 0:
        print(f"\nKB retrieval accuracy     : {agg['kb_correct']}/{agg['kb_total']} "
              f"({agg['kb_correct']/agg['kb_total']*100:.1f}%)  "
              f"— top-returned chunk's section matched the labeled correct section")
        print(f"KB search latency         : p50 {percentile(kb_sorted, 0.50):.3f}s   "
              f"p95 {percentile(kb_sorted, 0.95):.3f}s")

    escalate_cases = [r for r in results if r["true_intent"] == "escalate"]
    if escalate_cases:
        escalate_correct = sum(r["intent_correct"] for r in escalate_cases)
        print(f"\nEscalation classification rate : {escalate_correct}/{len(escalate_cases)} "
              f"({escalate_correct/len(escalate_cases)*100:.1f}%)")
        print("  (this measures classifier routing accuracy on escalate-worthy")
        print("   messages only — NOT full-conversation escalation rate, which")
        print("   also includes failed-ID-retry and KB-miss escalations)")

    print("\nPer-intent breakdown:")
    for true_intent, preds in sorted(agg["intent_confusion"].items()):
        total = sum(preds.values())
        correct = preds.get(true_intent, 0)
        print(f"  {true_intent:10s}: {correct}/{total} correct  ({correct/total*100:.1f}%)")
        for pred, count in preds.items():
            if pred != true_intent:
                print(f"      -> misclassified as '{pred}': {count}")

    if agg["lang_confusion"]:
        print("\nPer-language breakdown:")
        for true_lang, preds in sorted(agg["lang_confusion"].items()):
            total = sum(preds.values())
            correct = preds.get(true_lang, 0)
            print(f"  {true_lang:10s}: {correct}/{total} correct  ({correct/total*100:.1f}%)")
            for pred, count in preds.items():
                if pred != true_lang:
                    print(f"      -> misclassified as '{pred}': {count}")


def save_csv(results, out_path="eval_results.csv"):
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"\nFull per-case results saved to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python eval_full.py test_set.jsonl")
        sys.exit(1)

    agg = asyncio.run(run_eval(sys.argv[1]))
    summarize(agg)
    save_csv(agg["results"])
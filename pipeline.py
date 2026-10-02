"""
Full pipeline: (contract evidence, hypothesis) -> FOL -> Narsese -> ONA -> label

Reports THREE separate numbers, matching the paper's own evaluation style:
  1. Narsese compile rate   -- did the FOL lines all convert to Narsese cleanly?
  2. ONA execution success  -- did ONA run and produce SOME answer?
  3. Final label accuracy   -- does the resulting label match ContractNLI's real label?

Keeping these separate tells you exactly which stage breaks when something
fails, instead of one blended "it got X% right" number.

Run:
    python3 pipeline.py
"""

import json
import os
import re
import sys

from fol_to_narsese import compile_fol, extract_polarity, fol_line_to_narsese
from fol_translator import retry_citation
from run_ona import run_narsese, frequency_to_label

# Optional: pass a filename to run a different batch, e.g.:
#   python3 pipeline.py eval_batch1.json
INPUT_FILE = sys.argv[1] if len(sys.argv) > 1 else "gold_examples.json"
PREDICTIONS_FILE = INPUT_FILE.replace(".json", "_fol_predictions.json")
OUTPUT_FILE = INPUT_FILE.replace(".json", "_pipeline_results.json")

# Map the paper's True/False/Uncertain onto ContractNLI's label names
LABEL_MAP = {
    "True": "Entailment",
    "False": "Contradiction",
    "Uncertain": "NotMentioned",
}


def extract_evidence_trace(fol_lines, real_evidence_text):
    """Pull out EVIDENCE: "..." lines, pairing each with the REL/QUERY
    line immediately before it. Checks each quote is an ACTUAL substring
    of the real evidence text -- this is what catches a hallucinated
    citation instead of just trusting the LLM said it quoted something.
    Returns (fol_lines_without_evidence, trace) where trace is a list of
    {"statement": ..., "quote": ..., "grounded": bool}.
    """
    cleaned = []
    trace = []
    pending_statement = None
    for line in fol_lines:
        stripped = line.strip()
        m = re.match(r'EVIDENCE:\s*"(.*)"\s*$', stripped)
        if m and pending_statement is not None:
            quote = m.group(1)
            grounded = bool(real_evidence_text) and quote in real_evidence_text
            trace.append({
                "fol_statement": pending_statement,
                "narsese_statement": fol_line_to_narsese(pending_statement),
                "quote": quote,
                "grounded": grounded,
            })
            # NOTE: ungrounded facts are no longer dropped here. pipeline's
            # main loop gives the model one retry first (see
            # retry_ungrounded_facts below), and only drops a fact if the
            # retry also fails to find real support.
            pending_statement = None
        else:
            cleaned.append(line)
            if stripped and not stripped.upper().startswith("POLARITY:"):
                pending_statement = stripped
    return cleaned, trace


def retry_ungrounded_facts(cleaned_fol_lines, trace, real_evidence_text):
    """For every fact whose first citation failed grounding, give the
    model ONE retry with the failure made explicit. If the retry finds a
    real, verifiable quote, keep the fact (with the corrected quote). If
    the retry also fails (or the model concedes NO_SUPPORT), drop the
    fact from the FOL before it ever reaches reasoning.

    Returns (fol_lines_after_retry, updated_trace, messages) -- messages
    is returned rather than printed here, so the caller can print it
    AFTER that example's own summary line instead of before (avoids it
    visually attaching to the previous example's output).
    """
    updated_trace = []
    lines_to_drop = set()
    messages = []

    for entry in trace:
        if entry["grounded"]:
            updated_trace.append(entry)
            continue

        corrected_quote = retry_citation(
            real_evidence_text, entry["fol_statement"], entry["quote"]
        )
        if corrected_quote and corrected_quote in real_evidence_text:
            entry = {**entry, "quote": corrected_quote, "grounded": True, "recovered_by_retry": True}
            messages.append(f"   \u2713 RETRY RECOVERED a real citation for: {entry['fol_statement']}")
            messages.append(f"     \"{corrected_quote}\"")
        else:
            lines_to_drop.add(entry["fol_statement"])
            entry = {**entry, "grounded": False, "dropped_after_retry": True}
            messages.append(f"   \u2717 RETRY FAILED -- dropping fact: {entry['fol_statement']}")
        updated_trace.append(entry)

    fol_lines_after_retry = [l for l in cleaned_fol_lines if l.strip() not in lines_to_drop]
    return fol_lines_after_retry, updated_trace, messages


def label_from_frequency(frequency, polarity):
    """Map an ONA frequency to Entailment/Contradiction/NotMentioned,
    accounting for whether the HYPOTHESIS itself is a prohibition.

    For a POSITIVE hypothesis ("Party may do X"): the query asks about X
    directly, so freq near 1 means the contract confirms X (Entailment),
    freq near 0 means the contract denies X (Contradiction).

    For a NEGATIVE hypothesis ("Party shall NOT do X"): the query still
    asks about the underlying positive action X (that's what gets
    represented in Narsese), so the mapping FLIPS -- freq near 0 means
    X doesn't happen, which CONFIRMS the "shall not" hypothesis
    (Entailment), and freq near 1 means X does happen, CONTRADICTING it.
    """
    tf_uncertain = frequency_to_label(frequency)  # True / False / Uncertain
    if tf_uncertain == "Uncertain":
        return "NotMentioned"
    if polarity == "POSITIVE":
        return "Entailment" if tf_uncertain == "True" else "Contradiction"
    else:  # NEGATIVE hypothesis
        return "Contradiction" if tf_uncertain == "True" else "Entailment"


def get_fol_lines_for_example(ex, predictions_by_id):
    """Use the LLM-predicted FOL if available (from fol_translator.py),
    otherwise fall back to the hand-written gold FOL if this example has
    one. If neither exists, there's nothing to compile."""
    if ex["id"] in predictions_by_id:
        predicted_text = predictions_by_id[ex["id"]]["predicted_fol"]
        return [l for l in predicted_text.split("\n") if l.strip()], "predicted"
    if "gold_fol" in ex:
        return ex["gold_fol"], "gold"
    return [], "missing"


def main():
    with open(INPUT_FILE) as f:
        examples = json.load(f)
    print(f"Running pipeline on {len(examples)} examples from {INPUT_FILE}")

    predictions_by_id = {}
    if os.path.exists(PREDICTIONS_FILE):
        with open(PREDICTIONS_FILE) as f:
            for row in json.load(f):
                predictions_by_id[row["id"]] = row
        print(f"Using LLM-predicted FOL from {PREDICTIONS_FILE}\n")
    else:
        print(f"No {PREDICTIONS_FILE} found -- using hand-written gold FOL instead.")
        print("(Run fol_translator.py first to test the full automated pipeline.)\n")

    results = []
    compiled_ok_count = 0
    ona_answered_count = 0
    label_correct_count = 0

    for ex in examples:
        fol_lines, fol_source = get_fol_lines_for_example(ex, predictions_by_id)
        polarity, fol_lines = extract_polarity(fol_lines)
        fol_lines, evidence_trace = extract_evidence_trace(fol_lines, ex.get("evidence", ""))
        retry_messages = []
        if any(not t["grounded"] for t in evidence_trace):
            fol_lines, evidence_trace, retry_messages = retry_ungrounded_facts(
                fol_lines, evidence_trace, ex.get("evidence", "")
            )
        narsese_lines, unrecognized = compile_fol(fol_lines)
        compiled_ok = len(unrecognized) == 0 and len(narsese_lines) > 0

        predicted_label = None
        frequency = None
        if compiled_ok:
            ona_result = run_narsese(narsese_lines)
            frequency = ona_result["frequency"]
            predicted_label = label_from_frequency(frequency, polarity)
            if frequency is not None:
                ona_answered_count += 1
            compiled_ok_count += 1
        else:
            predicted_label = "COMPILE_ERROR"

        is_correct = predicted_label == ex["correct_label"]
        if is_correct:
            label_correct_count += 1

        results.append({
            "id": ex["id"],
            "hypothesis": ex["hypothesis"],
            "fol_source": fol_source,
            "polarity": polarity,
            "evidence_trace": evidence_trace,
            "narsese_lines": narsese_lines,
            "unrecognized_fol_lines": unrecognized,
            "frequency": frequency,
            "predicted_label": predicted_label,
            "correct_label": ex["correct_label"],
            "match": is_correct,
        })

        print(f"[{ex['id']}] ({fol_source} FOL) "
              f"predicted={predicted_label} correct={ex['correct_label']} "
              f"{'OK' if is_correct else 'WRONG'}")
        if unrecognized:
            print(f"   unrecognized FOL lines: {unrecognized}")
        for msg in retry_messages:
            print(msg)

    n = len(examples)
    print("\n--- Summary ---")
    print(f"Narsese compile rate:  {compiled_ok_count}/{n} "
          f"({100*compiled_ok_count/n:.0f}%)")
    print(f"ONA produced an answer: {ona_answered_count}/{n} "
          f"({100*ona_answered_count/n:.0f}%)")
    print(f"Final label accuracy:  {label_correct_count}/{n} "
          f"({100*label_correct_count/n:.0f}%)")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

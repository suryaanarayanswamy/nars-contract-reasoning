"""
PIPELINE B: LLM translates straight to Narsese (no FOL stage, no mechanical
compiler). Self-correction comes from a back-translation fidelity check
against the EVIDENCE (not the hypothesis, not the gold label -- checking
against the answer here would leak it into generation).

Run:
    python3 pipeline_b.py eval_batch1.json
"""

import json
import sys

from direct_translator_b import (
    translate_direct, parse_direct_output,
    back_translate_fact, judge_fidelity, retry_direct_statement,
)
from run_ona import run_narsese, frequency_to_label
from pipeline import label_from_frequency  # reuse Pipeline A's polarity-aware mapping

INPUT_FILE = sys.argv[1] if len(sys.argv) > 1 else "eval_batch1.json"
OUTPUT_FILE = INPUT_FILE.replace(".json", "_pipelineB_results.json")

LABEL_MAP = {"True": "Entailment", "False": "Contradiction", "Uncertain": "NotMentioned"}


def verify_and_finalize_facts(fact_entries, real_evidence_text):
    """For each asserted fact: check grounding, then fidelity. If either
    fails, retry once. Drop the fact if it still fails after retry.
    Returns (final_statements, trace_for_reporting)."""
    final_statements = []
    trace = []

    for entry in fact_entries:
        statement, quote = entry["statement"], entry["quote"]

        grounded = bool(quote) and quote in real_evidence_text
        fidelity_verdict = "SKIPPED"
        if grounded:
            back_translated = back_translate_fact(statement)
            fidelity_verdict, _ = judge_fidelity(real_evidence_text, back_translated)

        passed = grounded and fidelity_verdict == "MATCH"

        if not passed:
            reason = "citation not found in evidence" if not grounded else f"fidelity check: {fidelity_verdict}"
            new_statement, new_quote = retry_direct_statement(
                real_evidence_text, statement, quote or "", reason
            )
            if new_statement and new_quote and new_quote in real_evidence_text:
                back_translated = back_translate_fact(new_statement)
                retry_verdict, _ = judge_fidelity(real_evidence_text, back_translated)
                if retry_verdict == "MATCH":
                    print(f"   \u2713 RETRY RECOVERED: {new_statement}")
                    final_statements.append(new_statement)
                    trace.append({"statement": new_statement, "quote": new_quote, "status": "recovered"})
                    continue
            print(f"   \u2717 RETRY FAILED -- dropping: {statement}")
            trace.append({"statement": statement, "quote": quote, "status": "dropped"})
            continue

        final_statements.append(statement)
        trace.append({"statement": statement, "quote": quote, "status": "ok"})

    return final_statements, trace


def main():
    with open(INPUT_FILE) as f:
        examples = json.load(f)
    print(f"Pipeline B: direct-to-Narsese translation on {len(examples)} examples from {INPUT_FILE}\n")

    results = []
    correct_count = 0

    for ex in examples:
        print(f"[{ex['id']}] translating directly to Narsese...")
        raw_output = translate_direct(ex.get("evidence", ""), ex["hypothesis"])
        polarity, fact_entries, query_line = parse_direct_output(raw_output)

        if fact_entries:
            final_statements, trace = verify_and_finalize_facts(fact_entries, ex.get("evidence", ""))
        else:
            final_statements, trace = [], []

        narsese_lines = final_statements + ([query_line] if query_line else [])

        if not narsese_lines or not query_line:
            predicted_label = "TRANSLATION_ERROR"
            frequency = None
        else:
            ona_result = run_narsese(narsese_lines)
            frequency = ona_result["frequency"]
            predicted_label = label_from_frequency(frequency, polarity)

        is_correct = predicted_label == ex["correct_label"]
        correct_count += is_correct

        results.append({
            "id": ex["id"],
            "hypothesis": ex["hypothesis"],
            "pipeline": "B",
            "polarity": polarity,
            "raw_llm_output": raw_output,
            "fact_trace": trace,
            "narsese_lines": narsese_lines,
            "frequency": frequency,
            "predicted_label": predicted_label,
            "correct_label": ex["correct_label"],
            "match": is_correct,
        })

        print(f"   predicted={predicted_label} correct={ex['correct_label']} "
              f"{'OK' if is_correct else 'WRONG'}\n")

    n = len(examples)
    print("--- Pipeline B Summary ---")
    print(f"Final label accuracy: {correct_count}/{n} ({100*correct_count/n:.0f}%)")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

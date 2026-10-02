"""
Back-translation check: Narsese -> English, compared against the original
hypothesis, as a supplementary sanity check alongside pipeline.py's
execution-based validation (which remains the primary check).

Run AFTER fol_translator.py and pipeline.py have produced their outputs.

Run:
    export OPENAI_API_KEY="sk-..."
    python3 back_translate.py
"""

import json
import sys
from openai import OpenAI

client = OpenAI()

# Optional: pass a filename to check a different batch, e.g.:
#   python3 back_translate.py eval_batch1.json
INPUT_FILE = sys.argv[1] if len(sys.argv) > 1 else "gold_examples.json"
PIPELINE_RESULTS = INPUT_FILE.replace(".json", "_pipeline_results.json")
OUTPUT_FILE = INPUT_FILE.replace(".json", "_back_translation_check.json")

SYSTEM_PROMPT = """You are given Narsese statements (a formal reasoning language).
Translate them back into a single plain English sentence describing what they claim.

CRITICAL: check every statement for a truth-value tag like "%0.00;0.90%" after
the period. A frequency near 0.00 means the statement is FALSE / NEGATED --
you must say "is NOT permitted" / "is prohibited", not the positive form.
A frequency near 1.00 (or no tag at all) means the statement is affirmed as
stated. Also: "<A --> B>" means "A is a kind of B" (non-exclusive) -- do NOT
phrase it as "only A is B" or imply exclusivity.

Output ONLY the English sentence, nothing else."""


def back_translate(narsese_lines):
    narsese_text = "\n".join(narsese_lines)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": narsese_text},
        ],
        temperature=0,
    )
    return response.choices[0].message.content.strip()


def judge_match(original_hypothesis, back_translated, correct_label):
    """Ask the model to judge the back-translation -- but what counts as
    'correct' depends on the label. For Entailment, a good translation
    should AGREE with the hypothesis. For Contradiction, a good
    translation should DISAGREE with it (state the opposite). That's not
    a flaw to catch -- it's the point."""
    if correct_label == "Entailment":
        instruction = (
            "The correct label is Entailment, meaning the contract AGREES "
            "with the hypothesis. A good back-translation should affirm "
            "the same claim as the hypothesis."
        )
    elif correct_label == "Contradiction":
        instruction = (
            "The correct label is Contradiction, meaning the contract "
            "DISAGREES with the hypothesis. A good back-translation should "
            "state the OPPOSITE of the hypothesis' claim -- that is the "
            "correct outcome here, not an error."
        )
    else:
        return "VERDICT: N/A\nREASON: NotMentioned case -- no evidence was asserted, so there is nothing to check the back-translation against."

    prompt = f"""Original hypothesis: "{original_hypothesis}"
Back-translated from Narsese: "{back_translated}"

{instruction}

Given that, does the back-translation correctly reflect what a system
reasoning about this contract SHOULD conclude?
Answer in this exact format:
VERDICT: MATCH or PARTIAL or MISMATCH
REASON: one sentence"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return response.choices[0].message.content.strip()


def main():
    with open(INPUT_FILE) as f:
        gold = {ex["id"]: ex for ex in json.load(f)}

    with open(PIPELINE_RESULTS) as f:
        pipeline_results = json.load(f)

    results = []
    for row in pipeline_results:
        ex_id = row["id"]
        narsese_lines = row["narsese_lines"]
        original_hypothesis = row["hypothesis"]

        if not narsese_lines:
            continue

        if row.get("predicted_label") == "COMPILE_ERROR":
            # Don't check partial/incomplete Narsese that the pipeline
            # itself already correctly rejected -- a MATCH here would be
            # checking a fragment, not the (failed) translation as a whole.
            print(f"[{ex_id}] skipped -- compile error, only a partial "
                  f"fragment exists, not a real translation to check\n")
            results.append({
                "id": ex_id,
                "original_hypothesis": original_hypothesis,
                "narsese_lines": narsese_lines,
                "back_translated": None,
                "judgment": "VERDICT: N/A\nREASON: COMPILE_ERROR -- only a partial fragment exists, not a complete translation.",
                "verdict": "N/A",
            })
            continue

        back_translated = back_translate(narsese_lines)
        judgment = judge_match(original_hypothesis, back_translated, row["correct_label"])

        print(f"[{ex_id}]")
        print("  original:        ", original_hypothesis)
        print("  narsese:          ", " | ".join(narsese_lines))
        print("  back-translated:  ", back_translated)
        print("  judgment:\n   ", judgment.replace("\n", "\n    "))
        print()

        # pull out just the verdict word (MATCH / PARTIAL / MISMATCH)
        verdict = "UNKNOWN"
        for line in judgment.splitlines():
            if line.strip().upper().startswith("VERDICT:"):
                verdict = line.split(":", 1)[1].strip().upper()
                break

        results.append({
            "id": ex_id,
            "original_hypothesis": original_hypothesis,
            "narsese_lines": narsese_lines,
            "back_translated": back_translated,
            "judgment": judgment,
            "verdict": verdict,
        })

    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)

    na_count = sum(1 for r in results if r["verdict"] == "N/A")
    applicable = [r for r in results if r["verdict"] != "N/A"]
    n_applicable = len(applicable)
    match_count = sum(1 for r in applicable if r["verdict"] == "MATCH")
    partial_count = sum(1 for r in applicable if r["verdict"] == "PARTIAL")
    mismatch_count = sum(1 for r in applicable if r["verdict"] == "MISMATCH")

    print("--- Back-translation summary ---")
    print(f"N/A (NotMentioned, no evidence to check): {na_count}/{len(results)}")
    if n_applicable:
        print(f"Of the {n_applicable} applicable (Entailment/Contradiction) cases:")
        print(f"  MATCH:    {match_count}/{n_applicable} ({100*match_count/n_applicable:.0f}%)")
        print(f"  PARTIAL:  {partial_count}/{n_applicable} ({100*partial_count/n_applicable:.0f}%)")
        print(f"  MISMATCH: {mismatch_count}/{n_applicable} ({100*mismatch_count/n_applicable:.0f}%)")
    print(f"\nSaved full details to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

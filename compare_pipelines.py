"""
Compares Pipeline A (LLM -> FOL -> mechanical compiler -> Narsese) against
Pipeline B (LLM -> Narsese directly, self-corrected via back-translation
fidelity checks) on the same examples.

Run AFTER both pipeline.py and pipeline_b.py have been run on the same
input file:
    python3 pipeline.py eval_batch1.json
    python3 pipeline_b.py eval_batch1.json
    python3 compare_pipelines.py eval_batch1.json
"""

import json
import sys

INPUT_FILE = sys.argv[1] if len(sys.argv) > 1 else "eval_batch1.json"
A_FILE = INPUT_FILE.replace(".json", "_pipeline_results.json")
B_FILE = INPUT_FILE.replace(".json", "_pipelineB_results.json")


def main():
    with open(A_FILE) as f:
        a_rows = {r["id"]: r for r in json.load(f)}
    with open(B_FILE) as f:
        b_rows = {r["id"]: r for r in json.load(f)}

    ids = sorted(set(a_rows) | set(b_rows), key=lambda x: (len(x), x))

    print(f"{'id':10} {'correct':14} {'A result':10} {'B result':10} {'agreement'}")
    print("-" * 65)

    a_correct = b_correct = both_correct = both_wrong = only_a = only_b = 0
    for ex_id in ids:
        a = a_rows.get(ex_id)
        b = b_rows.get(ex_id)
        correct = (a or b)["correct_label"]
        a_label = a["predicted_label"] if a else "?"
        b_label = b["predicted_label"] if b else "?"
        a_ok = a and a["match"]
        b_ok = b and b["match"]

        if a_ok:
            a_correct += 1
        if b_ok:
            b_correct += 1
        if a_ok and b_ok:
            both_correct += 1
            tag = "both correct"
        elif not a_ok and not b_ok:
            both_wrong += 1
            tag = "both wrong"
        elif a_ok and not b_ok:
            only_a += 1
            tag = "only A correct"
        else:
            only_b += 1
            tag = "only B correct"

        print(f"{ex_id:10} {correct:14} {a_label:10} {b_label:10} {tag}")

    n = len(ids)
    print("\n--- Summary ---")
    print(f"Pipeline A accuracy: {a_correct}/{n} ({100*a_correct/n:.0f}%)")
    print(f"Pipeline B accuracy: {b_correct}/{n} ({100*b_correct/n:.0f}%)")
    print()
    print(f"Both correct:    {both_correct}")
    print(f"Both wrong:      {both_wrong}")
    print(f"Only A correct:  {only_a}  (cases where the mechanical compiler helped)")
    print(f"Only B correct:  {only_b}  (cases where direct translation helped)")


if __name__ == "__main__":
    main()

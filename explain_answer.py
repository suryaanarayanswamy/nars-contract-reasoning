"""
Shows WHICH original Narsese statements ONA actually combined to reach
its answer -- not just the final frequency/confidence. ONA tracks this
itself via each statement's "Stamp=[...]" (its evidential base), this
script just reads that out and matches the stamp numbers back to the
actual statement text.

Usage 1 -- explain an example from an existing pipeline run:
    python3 explain_answer.py eval_batch1_pipeline_results.json eval_14

Usage 2 -- paste Narsese lines directly:
    python3 explain_answer.py
    (paste lines, one per line, then an empty line to run)
"""

import re
import sys
import json

from run_ona import run_narsese


def build_stamp_map(raw_output):
    """Map each root input's stamp id -> its exact Narsese statement text.
    Only ground facts (lines ending in '.') get a stamp this way; a bare
    query ('?') doesn't, since it isn't itself evidence for anything."""
    stamp_map = {}
    for line in raw_output.splitlines():
        m = re.match(r"Input:\s*(.+\.)\s+Priority=.*?Stamp=\[(\d+)\]", line.strip())
        if m:
            statement, stamp_id = m.group(1), int(m.group(2))
            stamp_map[stamp_id] = statement
    return stamp_map


def find_answer_trace(raw_output):
    """Find the final Answer line and the stamp ids it was built from."""
    answer_lines = [l for l in raw_output.splitlines() if l.strip().startswith("Answer:")]
    if not answer_lines:
        return None, []
    last = answer_lines[-1]
    m = re.search(r"Answer:\s*(.+?)\s+creationTime=.*?Stamp=\[([\d,]+)\]", last)
    if not m:
        return None, []
    conclusion = m.group(1)
    stamp_ids = [int(x) for x in m.group(2).split(",")]
    return conclusion, stamp_ids


def build_evidence_lookup(evidence_trace):
    """Map a compiled Narsese statement -> its {quote, grounded} info,
    so we can show the natural-language source next to each premise."""
    lookup = {}
    for entry in evidence_trace or []:
        if entry.get("narsese_statement"):
            lookup[entry["narsese_statement"]] = entry
    return lookup


def explain(narsese_lines, evidence_trace=None):
    print("Narsese fed to ONA:")
    for line in narsese_lines:
        print(" ", line)
    print()

    result = run_narsese(narsese_lines)
    raw_output = result["raw_output"]
    stamp_map = build_stamp_map(raw_output)
    conclusion, stamp_ids = find_answer_trace(raw_output)
    evidence_lookup = build_evidence_lookup(evidence_trace)

    if conclusion is None:
        print("ONA gave NO answer -- it has no relevant belief at all for this query.")
        print("(This is the correct outcome for a NotMentioned case: no evidence, no guess.)")
        return

    print(f"Conclusion: {conclusion}")
    print(f"Truth: frequency={result['frequency']}, confidence={result['confidence']}")
    print()

    if not stamp_ids:
        print("(ONA didn't report which statements it used -- this conclusion may have come")
        print(" directly from a single asserted fact rather than a derivation.)")
        return

    print("Statements ONA actually combined to reach this, with their source text:")
    seen = set()
    for sid in stamp_ids:
        stmt = stamp_map.get(sid)
        if stmt is None or stmt in seen:
            continue
        seen.add(stmt)
        print(f"  [{sid}] {stmt}")
        info = evidence_lookup.get(stmt)
        if info is None:
            print(f"        (no evidence citation recorded for this statement)")
        elif info["grounded"]:
            print(f"        \u2713 from contract: \"{info['quote']}\"")
        else:
            print(f"        \u26a0 UNGROUNDED -- claimed quote not found in the actual evidence: \"{info['quote']}\"")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        results_file, example_id = sys.argv[1], sys.argv[2]
        with open(results_file) as f:
            rows = json.load(f)
        row = next((r for r in rows if r["id"] == example_id), None)
        if row is None:
            print(f"No example with id '{example_id}' found in {results_file}")
            sys.exit(1)
        if row.get("hypothesis"):
            print(f"Hypothesis: {row['hypothesis']}\n")
        explain(row["narsese_lines"], row.get("evidence_trace"))
    else:
        print("Paste Narsese lines (one per line), then an empty line to run:")
        lines = []
        while True:
            line = input()
            if not line.strip():
                break
            lines.append(line)
        explain(lines)

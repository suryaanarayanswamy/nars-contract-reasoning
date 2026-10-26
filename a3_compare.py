"""Side-by-side: plain LLM vs pipeline (and multi-agent) on the same rows.
  python3 a3_compare.py eval_fresh60_baseline_results.json eval_fresh60_a3_results.json [eval_fresh60_multi_results.json]"""
import json, sys
from collections import Counter

LABELS = ("Entailment", "Contradiction", "NotMentioned")
names = ["plain LLM", "pipeline (LLM+NARS)", "multi-agent pipeline"]
sets = [{r["id"]: r for r in json.load(open(p))} for p in sys.argv[1:]]
ids = [i for i in sets[0] if all(i in s for s in sets)]
print(f"rows compared: {len(ids)}\n")
print(f"{'system':24s} {'overall':>10s}  " + "  ".join(f"{l:>14s}" for l in LABELS))
for nm, s in zip(names, sets):
    tot = sum(s[i]["predicted_label"] == s[i]["correct_label"] for i in ids)
    per = []
    for l in LABELS:
        rows = [i for i in ids if s[i]["correct_label"] == l]
        per.append(f"{sum(s[i]['predicted_label'] == l for i in rows)}/{len(rows)}")
    print(f"{nm:24s} {tot:>4d}/{len(ids)} {tot / len(ids):4.0%}  " + "  ".join(f"{p:>14s}" for p in per))
if len(sets) >= 2:
    a, b = sets[0], sets[1]
    only_a = [i for i in ids if a[i]["match"] and not b[i]["match"]]
    only_b = [i for i in ids if b[i]["match"] and not a[i]["match"]]
    print(f"\nplain LLM right, pipeline wrong: {len(only_a)} {only_a}\npipeline right, plain LLM wrong: {len(only_b)} {only_b}")
    print(f"both wrong: {sum(1 for i in ids if not a[i]['match'] and not b[i]['match'])}")

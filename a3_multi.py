"""Multi-agent check. Several independent agents (different points of view) each run the WHOLE pipeline
(translate contract + claim, check, repair, align, compile, ONA). A vote decides the label; disagreement is reported.

  python3 a3_multi.py eval_ret_recon.json --agents 3            # AI agents (needs OPENAI_API_KEY)
  python3 a3_multi.py eval17.json --self-test                    # no AI: tests the voting logic with gold + damaged translations
"""
import argparse, json, os, sys
from collections import Counter
import a3_run as R

PERSONAS = [
    "",   # agent 0: the standard reading
    "You are a careful contract lawyer. Be especially attentive to exceptions, conditions, 'unless', 'save that', and to permissions that the "
    "passage clearly implies without stating (rule 9). Never drop a qualifier.",
    "You are a formal logician. Be especially attentive to SCOPE: exactly what each act applies to, lists that must be split one act per verb "
    "and one item per kind, and definitions (rule 10). Prefer the narrowest faithful reading of each verb.",
    "You are a skeptical reviewer. Translate exactly what the passage says and nothing more; use 'inferred' only where rule 9 requires it.",
]


def vote(results):
    """results: list of process() dicts for the SAME row -> (label, how, labels)."""
    labels = [r["predicted_label"] for r in results]
    c = Counter(labels).most_common()
    if len(c) == 1:
        return c[0][0], "unanimous", labels
    if c[0][1] > c[1][1]:
        return c[0][0], f"majority {c[0][1]}/{len(labels)}", labels
    # tie: prefer the label whose agents were most confident in ONA
    best = {}
    for r in results:
        conf = (r.get("lenient") or {}).get("confidence") or 0
        best[r["predicted_label"]] = max(best.get(r["predicted_label"], 0), conf)
    tied = [l for l, n in c if n == c[0][1]]
    return max(tied, key=lambda l: best.get(l, 0)), "tie, broken by ONA confidence", labels


def run_row(ex, agents):
    """agents: list of (translator, aligner). -> merged result."""
    rs = [R.process(ex, tr, al) for tr, al in agents]
    label, how, labels = vote(rs)
    pick = max((r for r in rs if r["predicted_label"] == label), key=lambda r: -len(r["flags"]))
    out = dict(pick)
    out.update({"predicted_label": label, "match": label == ex["correct_label"], "vote": how, "agent_labels": labels,
                "agent_flags": [len(r["flags"]) for r in rs]})
    return out, rs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input"); ap.add_argument("--agents", type=int, default=3)
    ap.add_argument("--models", default=None, help="one model per agent, comma separated, e.g. gpt-4o,groq:llama-3.3-70b-versatile,ollama:llama3.1:8b")
    ap.add_argument("--model", default="gpt-4o"); ap.add_argument("--verify-model", default=None)
    ap.add_argument("--only", default=None); ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--gold", default="a3_gold.json")
    a = ap.parse_args()
    data = json.load(open(a.input))
    if a.only:
        keep = set(a.only.split(",")); data = [x for x in data if x["id"] in keep]
    if a.self_test:
        import a3_align as AL
        agents = [(R.GoldTranslator(a.gold), AL.OracleAligner()) for _ in range(a.agents)]
    else:
        from a3_translate import LLMTranslator
        agents = []
        ms = [m.strip() for m in a.models.split(",")] if a.models else []
        if ms:
            a.agents = len(ms)
        for i in range(a.agents):
            m = ms[i] if ms else a.model
            t = LLMTranslator(model=m, verify_model=a.verify_model or m, persona=PERSONAS[i % len(PERSONAS)])
            agents.append((t, t))
    out, per_agent = [], [[] for _ in agents]
    for ex in data:
        r, rs = run_row(ex, agents)
        out.append(r)
        for i, x in enumerate(rs):
            per_agent[i].append(x["match"])
        print(f"[{r['id']}] vote {r['predicted_label']:13s} (gold {r['correct_label']}) {'OK ' if r['match'] else 'XX '} "
              f"{r['vote']:28s} agents={r['agent_labels']}", flush=True)
    base = os.path.splitext(a.input)[0] + "_multi"
    json.dump(out, open(base + "_results.json", "w"), indent=1)
    R.write_report(out, base + "_report.md")
    n = len(out)
    print(f"\nMULTI-AGENT ({len(agents)} agents) accuracy: {sum(r['match'] for r in out)}/{n} ({sum(r['match'] for r in out) / n:.0%})")
    for i, m in enumerate(per_agent):
        print(f"  agent {i} alone: {sum(m)}/{n} ({sum(m) / n:.0%})")
    dis = [r for r in out if r["vote"] != "unanimous"]
    print(f"  rows where agents disagreed: {len(dis)}  -> {[r['id'] for r in dis]}")
    print(f"Saved {base}_results.json, {base}_report.md")


if __name__ == "__main__":
    main()

"""
Pipeline A3: lossless translation -> checks -> Narsese -> ONA -> label.

  python3 a3_run.py eval_ret_gold.json --translator gold  --gold a3_gold.json     # hand translations (no API)
  python3 a3_run.py eval_ret_gold.json --translator llm   [--model gpt-4o]        # AI translates (needs OPENAI_API_KEY)

Writes <input>_a3_results.json, <input>_a3_report.md and one <input>_a3_kb/<id>.nal per example (the complete
Narsese knowledge base: load it into ONA yourself and ask anything).
"""
import argparse, json, os, sys
import a2_compile as C
import a2_ona as O
import a2_vocab as V
import a3_core as K
import a3_align as AL

ORDERS = ("orig", "rev", "asm_mid", "asm_first")


def translate_hypothesis(text, translator):
    """The hypothesis goes through the SAME open translation as the contract. -> (stmt or None, flags)"""
    raw = translator.hypothesis_frame(text)
    stmt, errs = K.validate_statement(raw) if raw else (None, ["no translation"])
    flags = []
    if not stmt:
        return None, [{"type": "hypothesis_invalid", "detail": "; ".join(errs)[:160]}]
    led = K.ledger(text, [stmt], [])
    flags += [{**f, "type": "hypothesis_" + f["type"]} for f in led["flags"]]
    real = [f for f in led["flags"] if f.get("level") != "info"]
    if real and hasattr(translator, "repair"):                  # one repair round, kept only if it loses less
        try:
            fixed = translator.repair(text, [stmt], real, [])
            if fixed and fixed.get("statements"):
                st2, e2 = K.validate_statement(fixed["statements"][0])
                if st2:
                    led2 = K.ledger(text, [st2], [])
                    r2 = [f for f in led2["flags"] if f.get("level") != "info"]
                    if len(r2) < len(real):
                        return st2, [{**f, "type": "hypothesis_" + f["type"]} for f in led2["flags"]]
        except Exception:
            pass
    return stmt, flags


def robust_run(axioms, base, extra, query, cycles=50):
    """ONA's answer can depend on the order lines are fed in. Try several orders; use any answer; flag conflicts."""
    ax = list(axioms)
    variants = {
        "orig": ax + base + extra,
        "asm_twice": ax + base + extra + extra,
        "rev": ax + base[::-1] + extra,
        "rules_twice": ax + base + base + extra,
    }
    runs = {}
    for name, lines in variants.items():
        res = O.run([l for l, _ in lines], query, cycles=cycles)
        res["lines"] = lines
        runs[name] = res
    answered = {n: r for n, r in runs.items() if r["frequency"] is not None}
    if not answered:
        return runs["orig"], "none", {n: None for n in runs}
    labels = {n: O.label_from_frequency(r["frequency"]) for n, r in answered.items()}
    from collections import Counter
    top = Counter(labels.values()).most_common()
    best_label = top[0][0] if len(top) == 1 or top[0][1] > top[1][1] else \
        O.label_from_frequency(max(answered.values(), key=lambda r: r["confidence"])["frequency"])
    pick = max((r for n, r in answered.items() if labels[n] == best_label), key=lambda r: r["confidence"])
    conflict = "conflict" if len(set(labels.values())) > 1 else "ok"
    return pick, conflict, {n: (O.label_from_frequency(r["frequency"]) if r["frequency"] is not None else None) for n, r in runs.items()}


def process(ex, translator, aligner, repair=True, with_details=False):
    ev = ex.get("evidence", "") or ""
    raw = translator.evidence(ex) if ev.strip() else {"statements": [], "ignored": []}
    if not isinstance(raw.get("statements"), list):
        raw["statements"] = []
    ignored = K.clean_ignored(raw.get("ignored"))

    def check(raw_stmts):
        stmts, errors = [], []
        for s in raw_stmts:
            clean, errs = K.validate_statement(s)
            if clean: stmts.append(clean)
            else: errors.append({"statement": s, "errors": errs})
        led = K.ledger(ev, stmts, ignored)
        flags = list(led["flags"]) + K.semantic_audit(stmts, ev)
        for e in errors:
            flags.append({"type": "invalid_statement", "detail": "; ".join(e["errors"])[:160]})
        if stmts and hasattr(translator, "verify"):
            flags += translator.verify(ev, [K.render(x) for x in stmts])
        return stmts, errors, led, flags

    real = lambda fl: [f for f in fl if f.get("level") != "info"]

    stmts, errors, led, flags = check(raw["statements"])
    repaired = 0
    for _ in range(2 if repair else 0):
        if not real(flags):
            break
        fixed = translator.repair(ev, raw["statements"], flags, ignored)
        if fixed is None:
            break
        s2, e2, l2, f2 = check([x for x in fixed["statements"] if x is not None] if isinstance(fixed.get("statements"), list) else [])
        if len(real(f2)) < len(real(flags)):
            ignored = K.clean_ignored(fixed.get("ignored", ignored))
            raw = {"statements": fixed["statements"], "ignored": ignored}
            stmts, errors, led, flags, repaired = s2, e2, l2, f2, repaired + 1
        else:
            break

    if ev.strip() and stmts and hasattr(translator, "implied"):      # second look: implied permissions the first pass did not write down
        try:
            extra_raw = [dict(x, inferred=True) for x in translator.implied(ev, raw["statements"])]
            good = [x for x in extra_raw if K.validate_statement(x)[0]]
            if good:
                s3, e3, l3, f3 = check(raw["statements"] + good)
                if len(real(f3)) <= len(real(flags)) + 1:       # accept unless it makes the translation visibly worse
                    raw = {"statements": raw["statements"] + good, "ignored": ignored}
                    stmts, errors, led, flags = s3, e3, l3, f3
        except Exception:
            pass

    hyp_stmt, hyp_flags = translate_hypothesis(ex["hypothesis"], translator)
    flags += hyp_flags
    hyp = K.hypothesis_from_stmt(hyp_stmt) if hyp_stmt else None
    if hyp is None:
        hyp = {"tuple": "(*, Unknown)", "pred": "Permitted", "desc": "(hypothesis could not be translated)", "n_units": 0}
    query = f"<{hyp['tuple']} --> {hyp['pred']}>?"
    units = K.flatten(stmts)
    alignment = []
    if units and hyp_stmt:
        for u, (rel, why) in zip(units, aligner.align(ex, hyp_stmt, hyp, units, stmts)):
            u["relation"], u["why"] = rel, why
            alignment.append({"stmt": u["stmt"], "text": u["desc"], "relation": rel, "why": why})
    units, links = K.link_carveouts(units)
    base, extra = K.compile_units(units, hyp)
    details = K.detail_lines(stmts)
    axioms = K.AX_LINES + [(l, None) for l in hyp.get("defs", [])]   # full AND/OR structure of a named hypothesis condition
    run_base = base + ([(l, ("d", s)) for l, s in details] if with_details else [])
    strict = O.run([l for l, _ in axioms + base], query)
    best, conflict, per_order = robust_run(axioms, run_base, extra, query)
    if best.get("error"):
        flags.append({"type": "ona_error", "detail": "ONA refused this knowledge base: " + best["error"]})
    if best.get("dropped"):
        flags.append({"type": "ona_dropped_lines", "detail": f"ONA silently dropped {best['dropped']} knowledge-base line(s): a term is too large for this ONA build. "
                                                              "Rebuild ONA with patch_ona.sh (bigger limits)."})
    label = O.label_from_frequency(best["frequency"])
    strict_label = O.label_from_frequency(strict["frequency"])

    used_units = sorted({best["lines"][i - 1][1] for i in best["used"]
                         if 0 < i <= len(best["lines"]) and isinstance(best["lines"][i - 1][1], int)})
    used_stmts = sorted({units[u]["stmt"] for u in used_units})
    used_axioms = sorted({K.AXIOMS[i][0] for i in range(len(K.AXIOMS))
                          if any(best["lines"][j - 1][0] == K.AXIOMS[i][2] for j in best["used"] if 0 < j <= len(best["lines"]))})
    qualifier = None
    if label != "NotMentioned" and strict_label != label:
        qualifier = "depends on conditions/exceptions the contract states (assumed in lenient mode)"
    if conflict == "conflict":
        flags.append({"type": "ona_order_conflict", "detail": f"ONA gave different labels for different input orders: {per_order}"})

    return {
        "id": ex["id"], "hypothesis": ex["hypothesis"], "hypothesis_logic": hyp, "hypothesis_english": hyp["desc"], "query": query,
        "alignment": alignment,
        "statements": stmts, "invalid_statements": errors, "ignored": ignored, "carveouts": links,
        "english": [K.render(s) for s in stmts],
        "ledger": {"covered_pct": led["covered_pct"], "n_content_words": led["n_content"],
                   "orphans": [o["word"] for o in led["orphans"]]},
        "flags": flags, "repaired": repaired,
        "narsese": {"axioms": [l for l, _ in axioms], "verdict_rules": [l for l, _ in base],
                    "assumed": [l for l, _ in extra], "detail": [l for l, _ in details]},
        "strict": {k: strict[k] for k in ("frequency", "confidence")},
        "lenient": {k: best[k] for k in ("frequency", "confidence")},
        "ona_orders": per_order,
        "used_statements": used_stmts, "used_axioms": used_axioms, "qualifier": qualifier,
        "predicted_label": label, "correct_label": ex.get("correct_label"),
        "match": label == ex.get("correct_label"),
    }


def write_kb(r, folder):
    os.makedirs(folder, exist_ok=True)
    n = r["narsese"]
    lines = ["// axioms"] + n["axioms"] + ["// contract rules (verdict layer)"] + n["verdict_rules"] + \
            ["// assumed (lenient mode)"] + n["assumed"] + ["// full detail layer: every verb/object/recipient/purpose/condition"] + \
            n["detail"] + ["// query for the hypothesis", r["query"], "50"]
    open(os.path.join(folder, r["id"] + ".nal"), "w").write("\n".join(lines) + "\n")


def write_report(results, path):
    L = ["# A3 translation report\n"]
    for r in results:
        h = r["hypothesis_logic"]
        L.append(f"## {r['id']}  - predicted **{r['predicted_label']}**, correct **{r['correct_label']}** {'OK' if r['match'] else 'WRONG'}")
        L.append(f"Hypothesis: {r['hypothesis']}")
        L.append(f"Hypothesis translated (same open format as the contract): {r['hypothesis_english']}")
        L.append(f"Hypothesis as ONE Narsese question: `{r['query']}`\n")
        if not r["statements"]:
            L.append("_No contract statements._\n")
        for i, s in enumerate(r["statements"]):
            L.append(f"- **S{i}** {r['english'][i]}\n  - quote: \"{s['quote']}\"")
        if r.get("alignment"):
            L.append("\nAlignment (the only step that compares contract and hypothesis; it only labels how they relate):")
            for a in r["alignment"]:
                L.append(f"  - S{a['stmt']} {a['relation'].upper():9s} {a['text'][:110]}  -- {a['why'][:120]}")
        if r["narsese"]["verdict_rules"]:
            L.append("\nVerdict rules:\n" + "\n".join("    " + x for x in r["narsese"]["verdict_rules"]))
        if r["ignored"]:
            L.append("\nIgnored (declared meaningless): " + "; ".join(f"\"{x['text'][:60]}\" ({x.get('why','')})" for x in K.clean_ignored(r["ignored"])))
        if r["carveouts"]: L.append("\nCarve-outs linked: " + ", ".join(f"S{q} permits an exception to S{p}" for p, q in r["carveouts"]))
        if r["qualifier"]: L.append(f"\nQualifier: {r['qualifier']}")
        if r["used_statements"]:
            L.append("\nAnswer derived from: " + ", ".join(f"S{i}" for i in r["used_statements"]) + (" + rules " + ", ".join(r["used_axioms"]) if r["used_axioms"] else ""))
        lg = r["ledger"]
        L.append(f"\nLedger: {lg['covered_pct']:.0%} of {lg['n_content_words']} content words accounted for; flags: {len(r['flags'])}; ONA orders: {r['ona_orders']}")
        if lg["orphans"]: L.append("  - NOT represented: " + " ".join(lg["orphans"]))
        for f in r["flags"]: L.append(f"  - FLAG {f['type']}: {f['detail']}")
        L.append("")
    open(path, "w").write("\n".join(L))


class GoldTranslator:
    def __init__(self, path): self.gold = json.load(open(path))
    def evidence(self, ex): return self.gold.get(ex["id"], {"statements": [], "ignored": []})
    def repair(self, *a, **k): return None
    def hypothesis_frame(self, text):
        hit = V.lookup_hypothesis(text)
        frames = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "a3_hyp_gold.json")))
        return frames.get(hit[0]) if hit else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input"); ap.add_argument("--translator", choices=["gold", "llm"], default="llm")
    ap.add_argument("--gold", default="a3_gold.json"); ap.add_argument("--no-repair", action="store_true")
    ap.add_argument("--model", default="gpt-4o"); ap.add_argument("--verify-model", default=None)
    ap.add_argument("--with-details", action="store_true", help="feed the detail layer to ONA too")
    ap.add_argument("--only", default=None, help="comma-separated ids")
    a = ap.parse_args()
    if not O.check_build():
        print("WARNING: this ONA build silently drops large statements (default size limits). Results will be unreliable.\n"
              "         Fix: bash patch_ona.sh <your ONA folder>   then   export ONA_PATH=<the folder it prints>\n", flush=True)
    data = json.load(open(a.input))
    if a.only:
        keep = set(a.only.split(",")); data = [x for x in data if x["id"] in keep]
    if a.translator == "gold":
        tr = GoldTranslator(a.gold); al = AL.OracleAligner()
    else:
        from a3_translate import LLMTranslator
        tr = LLMTranslator(model=a.model, verify_model=a.verify_model); al = tr
    out = []
    for ex in data:
        r = process(ex, tr, al, repair=not a.no_repair, with_details=a.with_details)
        out.append(r)
        print(f"[{r['id']}] {r['predicted_label']:13s} (gold {r['correct_label']}) {'OK ' if r['match'] else 'XX '}"
              f"ledger {r['ledger']['covered_pct']:.0%}  flags {len(r['flags'])}", flush=True)
    base = os.path.splitext(a.input)[0] + "_a3"
    json.dump(out, open(base + "_results.json", "w"), indent=1)
    write_report(out, base + "_report.md")
    for r in out: write_kb(r, base + "_kb")
    n = len(out); ok = sum(r["match"] for r in out)
    print(f"\nA3 accuracy: {ok}/{n} ({ok / n:.0%})")
    for lab in ("Entailment", "Contradiction", "NotMentioned"):
        rows = [r for r in out if r["correct_label"] == lab]
        if rows: print(f"  {lab}: {sum(r['match'] for r in rows)}/{len(rows)}")
    cov = [r["ledger"]["covered_pct"] for r in out if r["ledger"]["n_content_words"]]
    print(f"Mean word coverage: {sum(cov) / len(cov):.0%} | rows with flags: {sum(1 for r in out if r['flags'])}")
    print(f"Saved {base}_results.json, {base}_report.md, {base}_kb/")


if __name__ == "__main__":
    main()

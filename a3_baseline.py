"""Plain-LLM baseline: the SAME model gets the SAME hypothesis and the SAME evidence text and answers directly (no translation, no ONA).
  python3 a3_baseline.py eval_fresh60.json [--model gpt-4o]        (needs OPENAI_API_KEY; type it only in your own terminal)"""
import argparse, json, os, hashlib

SYSTEM = """You are given a passage from a Non-Disclosure Agreement and a claim about the agreement.
Decide whether the passage:
  Entailment    - supports the claim (the claim follows from the passage)
  Contradiction - contradicts the claim (the passage says the opposite or rules it out)
  NotMentioned  - the passage does not address the claim (or no passage is given)
Output ONLY JSON: {"label": "Entailment|Contradiction|NotMentioned", "reason": "<one sentence>"}"""
LABELS = ("Entailment", "Contradiction", "NotMentioned")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("input"); ap.add_argument("--model", default="gpt-4o")
    a = ap.parse_args()
    from openai import OpenAI
    client = OpenAI()
    cache_file = os.environ.get("BASELINE_CACHE", "a3_baseline_cache.json")
    cache = json.load(open(cache_file)) if os.path.exists(cache_file) else {}
    data = json.load(open(a.input)); out = []
    for ex in data:
        user = f"Passage:\n{ex.get('evidence', '').strip() or '(no passage)'}\n\nClaim: {ex['hypothesis']}\n\nOutput:"
        k = hashlib.sha1(f"{a.model}|{user}".encode()).hexdigest()
        if k not in cache:
            r = client.chat.completions.create(model=a.model, temperature=0, response_format={"type": "json_object"},
                                               messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}])
            try:
                cache[k] = json.loads(r.choices[0].message.content)
            except Exception:
                cache[k] = {"label": "NotMentioned", "reason": "unparseable"}
            json.dump(cache, open(cache_file, "w"))
        lab = cache[k].get("label"); lab = lab if lab in LABELS else "NotMentioned"
        out.append({"id": ex["id"], "hypothesis": ex["hypothesis"], "predicted_label": lab, "correct_label": ex["correct_label"],
                    "match": lab == ex["correct_label"], "reason": cache[k].get("reason", "")})
        print(f"[{ex['id']}] {lab:13s} (gold {ex['correct_label']}) {'OK' if lab == ex['correct_label'] else 'XX'}", flush=True)
    base = os.path.splitext(a.input)[0] + "_baseline"
    json.dump(out, open(base + "_results.json", "w"), indent=1)
    n = len(out); ok = sum(r["match"] for r in out)
    print(f"\nPLAIN LLM accuracy: {ok}/{n} ({ok / n:.0%})")
    for l in LABELS:
        rows = [r for r in out if r["correct_label"] == l]
        if rows: print(f"  {l}: {sum(r['match'] for r in rows)}/{len(rows)}")
    print(f"Saved {base}_results.json")


if __name__ == "__main__":
    main()

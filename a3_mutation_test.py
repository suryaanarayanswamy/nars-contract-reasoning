"""Does the checker notice when a translation LOSES meaning? Damage correct translations in one way each and count catches.
No AI and no ONA: just the ledger + semantic audit.   python3 a3_mutation_test.py eval17.json a3_gold.json"""
import copy, json, sys
import a3_core as K

def flags_for(ev, raw, ignored):
    stmts = [K.validate_statement(s)[0] for s in raw]
    stmts = [s for s in stmts if s]
    led = K.ledger(ev, stmts, ignored)
    return [f for f in led["flags"] + K.semantic_audit(stmts, ev) if f.get("level") != "info"]

def mutants(raw):
    for si, s in enumerate(raw):
        if len(s["acts"]) > 1:
            m = copy.deepcopy(raw); del m[si]["acts"][-1]; yield "drop_one_verb", m
        if s["items"] and len(s["items"]) > 1:
            m = copy.deepcopy(raw); del m[si]["items"][-1]; yield "drop_one_item", m
        if s["details"]:
            m = copy.deepcopy(raw); del m[si]["details"][-1]; yield "drop_detail", m
        for k in ("recipient", "purpose", "manner", "time", "source"):
            for ai, a in enumerate(s["acts"]):
                if k in a["slots"]:
                    m = copy.deepcopy(raw); del m[si]["acts"][ai]["slots"][k]; yield "drop_slot_" + k, m
                    break
        if s["conditions"]:
            m = copy.deepcopy(raw); m[si]["conditions"] = []; yield "drop_condition", m
        if s["exceptions"]:
            m = copy.deepcopy(raw); m[si]["exceptions"] = []; yield "drop_exception", m
        if len(raw) > 1:
            m = copy.deepcopy(raw); del m[si]; yield "drop_statement", m
        if s["force"] in ("prohibition", "permission") and not s.get("inferred"):
            m = copy.deepcopy(raw); m[si]["force"] = "permission" if s["force"] == "prohibition" else "prohibition"; yield "flip_force", m

data = {x["id"]: x for x in json.load(open(sys.argv[1]))}
gold = json.load(open(sys.argv[2]))
tot, caught, by = 0, 0, {}
for rid, g in gold.items():
    ev = data[rid]["evidence"]
    for kind, m in mutants(g["statements"]):
        tot += 1
        hit = bool(flags_for(ev, m, g.get("ignored", [])))
        caught += hit
        t = by.setdefault(kind, [0, 0]); t[0] += 1; t[1] += hit
print(f"damaged translations: {tot}   caught by the checker: {caught} ({caught/tot:.0%})")
for k, (n, c) in sorted(by.items()): print(f"  {k:22s} {c}/{n}")
print("baseline (undamaged) rows with real flags:", sum(bool(flags_for(data[r]['evidence'], g['statements'], g.get('ignored', []))) for r, g in gold.items()), "of", len(gold))

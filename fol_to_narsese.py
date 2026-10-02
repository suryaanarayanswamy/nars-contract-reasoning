"""
Step 2 of the pipeline: FOL -> Narsese (deterministic, rule-based)

This is intentionally NOT an AI call -- it's plain pattern matching,
mirroring how the Gabriel & Wang paper's FOL-to-Narsese step is a fixed
compiler, not another model. It only handles the FOL shapes you've
actually seen in your data so far. When you hit a new shape, add a new
rule here rather than reaching for another LLM call.

Run standalone to self-test against gold_examples.json:
    python3 fol_to_narsese.py
"""

import json
import re

GOLD_FILE = "gold_examples.json"


def fol_line_to_narsese(line: str):
    """Convert ONE line of FOL into ONE line of Narsese, or return None
    if this rule set doesn't recognize the pattern."""
    line = line.strip()
    is_query = line.startswith("QUERY:")
    if is_query:
        line = line[len("QUERY:"):].strip()

    # --- Two-argument relations (new) ---
    # These keep BOTH the actor and the object in the term, instead of
    # collapsing everything into one atomic term like <ThirdParty --> Permitted>.
    # That's what was getting lost in back-translation.

    # If the line contains an implication arrow, ONLY the implication rule
    # may handle it -- never fall through to the plain-fact rule below,
    # which used to silently grab just the prefix of a line it didn't
    # actually understand and produce a wrong, duplicated fact.
    if "->" in line:
        m = re.fullmatch(
            r"REL:\s*(\w+)\(([\w]+),\s*([\w]+)\)\s*->\s*(\w+)\(([\w]+),\s*([\w]+)\)",
            line,
        )
        if not m:
            return None  # different args, nested terms, etc. -- not supported yet
        pred1, a1, b1, pred2, a2, b2 = m.groups()
        if (a1, b1) != (a2, b2):
            return None  # only same-argument implications are supported
        term = f"(*, {a1}, {b1})"
        if is_query:
            return f"<{term} --> {pred2}>?"
        return f"<<{term} --> {pred1}> ==> <{term} --> {pred2}>>."

    # Pattern: REL: [NOT] Pred(Arg1, Arg2)   [ground fact or query]
    # fullmatch, not match -- a line that has trailing junk after this
    # shape should be rejected, not silently truncated and accepted.
    m = re.fullmatch(r"REL:\s*(NOT\s+)?(\w+)\(([\w]+),\s*([\w]+)\)", line)
    if m:
        neg, pred, a, b = m.groups()
        term = f"(*, {a}, {b})"
        if is_query:
            return f"<{term} --> {pred}>?"
        if neg:
            return f"<{term} --> {pred}>. %0.00;0.90%"
        return f"<{term} --> {pred}>."

    # --- One-argument (unary) patterns (original) ---

    # Pattern: forall x (A(x) AND NOT B(x) -> NOT C(x))
    m = re.match(
        r"forall x \(([A-Za-z]+)\(x\) AND NOT [A-Za-z]+\(x\) -> NOT ([A-Za-z]+)\(x\)\)",
        line,
    )
    if m:
        subj, pred = m.group(1), m.group(2)
        # Simplification: we drop the "unless Authorized" condition and
        # just collapse to the subject term. This loses a nuance (a real
        # limitation worth naming in your report), but keeps the term
        # consistent with how a plain query about the same subject reads.
        if is_query:
            return f"<{subj} --> {pred}>?"
        return f"<{subj} --> {pred}>. %0.00;0.90%"  # negative belief

    # Pattern: forall x (A(x) -> NOT B(x))
    m = re.match(r"forall x \(([A-Za-z]+)\(x\) -> NOT ([A-Za-z]+)\(x\)\)", line)
    if m:
        subj, pred = m.group(1), m.group(2)
        if is_query:
            return f"<{subj} --> {pred}>?"
        return f"<{subj} --> {pred}>. %0.00;0.90%"

    # Pattern: forall x (A(x) -> B(x))   [plain positive implication]
    m = re.match(r"forall x \(([A-Za-z]+)\(x\) -> ([A-Za-z]+)\(x\)\)", line)
    if m:
        subj, pred = m.group(1), m.group(2)
        if is_query:
            return f"<{subj} --> {pred}>?"
        return f"<{subj} --> {pred}>."

    return None  # unrecognized pattern -- needs a new rule


def extract_polarity(fol_lines):
    """Look for a 'POLARITY: POSITIVE' or 'POLARITY: NEGATIVE' line.
    Returns (polarity, remaining_lines). Defaults to POSITIVE if absent
    (keeps old FOL without a polarity line working as before)."""
    polarity = "POSITIVE"
    remaining = []
    for line in fol_lines:
        stripped = line.strip()
        if stripped.upper().startswith("POLARITY:"):
            value = stripped.split(":", 1)[1].strip().upper()
            if value in ("POSITIVE", "NEGATIVE"):
                polarity = value
        else:
            remaining.append(line)
    return polarity, remaining


def compile_fol(fol_lines):
    """Convert a list of FOL lines into a list of Narsese lines.
    Returns (narsese_lines, unrecognized_lines)."""
    narsese_lines = []
    unrecognized = []
    for line in fol_lines:
        if not line.strip():
            continue
        result = fol_line_to_narsese(line)
        if result is None:
            unrecognized.append(line)
        else:
            narsese_lines.append(result)
    return narsese_lines, unrecognized


def self_test():
    """Run the compiler on your gold FOL and check it reproduces the
    gold Narsese you hand-wrote earlier."""
    with open(GOLD_FILE) as f:
        examples = json.load(f)

    passed, failed = 0, 0
    for ex in examples:
        narsese, unrecognized = compile_fol(ex["gold_fol"])
        expected = ex["gold_narsese"]
        ok = narsese == expected
        print(f"[{ex['id']}] {'PASS' if ok else 'FAIL'}")
        if not ok:
            print("   compiled:", narsese)
            print("   expected:", expected)
            if unrecognized:
                print("   unrecognized FOL lines:", unrecognized)
        if ok:
            passed += 1
        else:
            failed += 1
    print(f"\n{passed}/{passed + failed} gold examples compiled correctly.")


if __name__ == "__main__":
    self_test()

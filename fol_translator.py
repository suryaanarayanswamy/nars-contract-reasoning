"""
Step 1 of the pipeline: Natural Language -> First-Order Logic (FOL)

Loads gold_examples.json, sends each example's evidence + hypothesis to
an LLM, asks it to produce FOL in the same style as our hand-written
examples (few-shot), and saves the predicted FOL next to the gold FOL
so you can compare them by eye.

Run:
    export OPENAI_API_KEY="sk-..."
    python3 fol_translator.py
"""

import json
import os
import re
import sys
from openai import OpenAI

client = OpenAI()  # reads OPENAI_API_KEY from environment

# Optional: pass a filename to translate a different batch, e.g.:
#   python3 fol_translator.py eval_batch1.json
INPUT_FILE = sys.argv[1] if len(sys.argv) > 1 else "gold_examples.json"
OUTPUT_FILE = INPUT_FILE.replace(".json", "_fol_predictions.json")

# Few-shot examples shown to the model, built from your own hand-written FOL.
# Uses two-argument relations -- REL: Pred(Actor, Object) -- instead of
# single-argument predicates, so the object (e.g. "Confidential Information")
# doesn't get dropped the way it did with unary terms.
FEW_SHOT_EXAMPLES = """
Example 1 (POSITIVE hypothesis; a chain: fact, then two implications; each fact has an EVIDENCE quote):
Evidence: "The obligations and restrictions imposed by this Agreement will not apply to any information that: d. was independently developed by the Recipient without use of the Discloser's Confidential Information; or"
Hypothesis: "Receiving Party may independently develop information similar to Confidential Information."
FOL:
POLARITY: POSITIVE
REL: IndependentlyDeveloped(ReceivingParty, ConfidentialInfo)
EVIDENCE: "was independently developed by the Recipient without use of the Discloser's Confidential Information"
REL: IndependentlyDeveloped(ReceivingParty, ConfidentialInfo) -> Excluded(ReceivingParty, ConfidentialInfo)
EVIDENCE: "The obligations and restrictions imposed by this Agreement will not apply to any information that"
REL: Excluded(ReceivingParty, ConfidentialInfo) -> Permitted(ReceivingParty, ConfidentialInfo)
EVIDENCE: "The obligations and restrictions imposed by this Agreement will not apply"
QUERY: REL: Permitted(ReceivingParty, ConfidentialInfo)

Example 2 (POSITIVE hypothesis; fact + one implication):
Evidence: "The Parties will: a. limit disclosure of any Confidential Information to its directors, officers, employees, agents or representatives (collectively \\"Representatives\\") who have a need to know such Confidential Information in connection with the Transaction, and only for that purpose;"
Hypothesis: "Receiving Party may share some Confidential Information with some third-parties (including consultants, agents and professional advisors)."
FOL:
POLARITY: POSITIVE
REL: Representative(ThirdParty, ConfidentialInfo)
EVIDENCE: "agents or representatives"
REL: Representative(ThirdParty, ConfidentialInfo) -> Permitted(ThirdParty, ConfidentialInfo)
EVIDENCE: "limit disclosure of any Confidential Information to its directors, officers, employees, agents or representatives"
QUERY: REL: Permitted(ThirdParty, ConfidentialInfo)

Example 3 (POSITIVE hypothesis, evidence says the OPPOSITE -- use NOT on the fact):
Evidence: "Recipient will not disclose or permit access to Confidential Information to contract workers, consultants or contractors of Recipient or its Affiliates unless authorized by Disclosing Party in writing..."
Hypothesis: "Receiving Party may share some Confidential Information with some third-parties (including consultants, agents and professional advisors)."
FOL:
POLARITY: POSITIVE
REL: NOT Permitted(ContractWorker, ConfidentialInfo)
EVIDENCE: "Recipient will not disclose or permit access to Confidential Information to contract workers, consultants or contractors"
QUERY: REL: Permitted(ContractWorker, ConfidentialInfo)

Example 4 (NEGATIVE hypothesis -- "shall not"/"may not"/"must not" -- evidence CONFIRMS the prohibition):
Evidence: "Receiving Party shall not, and shall not permit any person to, reverse engineer any objects which embody Disclosing Party's Confidential Information."
Hypothesis: "Receiving Party shall not reverse engineer any objects which embody Disclosing Party's Confidential Information."
FOL:
POLARITY: NEGATIVE
REL: NOT Permitted(ReceivingParty, ReverseEngineer)
EVIDENCE: "Receiving Party shall not, and shall not permit any person to, reverse engineer"
QUERY: REL: Permitted(ReceivingParty, ReverseEngineer)

Example 5 (evidence is EMPTY -- contract never addresses this -- output ONLY polarity + query, no facts, no EVIDENCE lines):
Evidence: ""
Hypothesis: "Receiving Party shall not use any Confidential Information for any purpose other than the purposes stated in Agreement."
FOL:
POLARITY: NEGATIVE
QUERY: REL: Permitted(ReceivingParty, OtherPurposeUse)
"""

SYSTEM_PROMPT = f"""You translate a contract clause (evidence) and a claim (hypothesis)
into First-Order Logic, in EXACTLY the style shown in these examples.

Rules:
- The FIRST line must always be "POLARITY: POSITIVE" or "POLARITY: NEGATIVE".
  Use NEGATIVE if the hypothesis itself is phrased as a prohibition
  ("shall not", "may not", "must not", "no right to..."). Use POSITIVE
  otherwise (including "shall", "may", "must" -- affirmative claims).
- IMPORTANT: regardless of polarity, always phrase the predicate and the
  QUERY around the underlying POSITIVE action (e.g. always query
  "Permitted(...)", never "Prohibited(...)" or "NOT ...(...)" in the
  query itself). The polarity line is what tells the reader how to
  interpret a low frequency -- don't also flip the query itself, or the
  two flips cancel out incorrectly.
- Every predicate takes exactly TWO arguments: an actor and an object,
  e.g. Permitted(ThirdParty, ConfidentialInfo) -- NEVER a single-argument
  predicate like Permitted(ThirdParty). Both arguments must come from the
  actual evidence/hypothesis, not be invented.
- Use short PascalCase names for actors, objects, and predicates. Use
  THE SAME predicate name in every fact and in the query when they refer
  to the same underlying action -- inventing a different word (e.g.
  asserting "Permitted" but querying "Allowed") breaks the connection.
- Each line is either a ground fact ("REL: Pred(Arg1, Arg2)"), a negative
  fact ("REL: NOT Pred(Arg1, Arg2)"), or an implication between two
  predicates over the SAME pair of arguments
  ("REL: Pred1(Arg1, Arg2) -> Pred2(Arg1, Arg2)"). Implications can only
  connect two predicates that share the exact same two arguments --
  don't write an implication between different actors/objects.
- IMMEDIATELY after every REL fact/implication line (never after QUERY),
  add one line: EVIDENCE: "<exact substring copied verbatim from Evidence>".
  This must be a real, exact quote -- copy-paste, don't paraphrase or
  summarize. It is what lets a human verify the fact wasn't invented.
- Always end with exactly one line starting "QUERY: REL: ".
- If evidence is empty, output ONLY the POLARITY line and the QUERY line.
- Output ONLY the FOL lines, nothing else -- no explanation, no markdown.

{FEW_SHOT_EXAMPLES}
"""


def translate_to_fol(evidence: str, hypothesis: str) -> str:
    user_prompt = f'Evidence: "{evidence}"\nHypothesis: "{hypothesis}"\nFOL:'
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    return response.choices[0].message.content.strip()


RETRY_SYSTEM_PROMPT = """You previously translated a contract clause into a logical fact and cited a
quote as your evidence for it. That exact quote was checked against the real evidence text and
was NOT found there verbatim -- it may have been paraphrased, misremembered, or came from
somewhere else (like the hypothesis) rather than the actual evidence.

You get ONE more chance. Look at the REAL evidence text below very carefully.
- If it actually DOES support the fact, respond with ONLY a corrected quote: a short
  EXACT substring copied verbatim from the evidence text (copy-paste, do not paraphrase).
  Wrap it in double quotes, nothing else.
- If, looking carefully, the evidence does NOT actually support this fact, respond with
  exactly: NO_SUPPORT

Respond with ONLY the quote in quotes, or exactly NO_SUPPORT. Nothing else."""


def retry_citation(real_evidence_text, fol_statement, failed_quote):
    """Give the model one more chance to find a real quote for a fact
    whose first citation didn't check out. Returns a corrected quote
    string, or None if the model concedes there's no real support."""
    user_prompt = (
        f'Fact that needs support: {fol_statement}\n'
        f'Your previous (incorrect) quote: "{failed_quote}"\n'
        f'Real evidence text: "{real_evidence_text}"\n'
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": RETRY_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    reply = response.choices[0].message.content.strip()
    if reply.upper().startswith("NO_SUPPORT"):
        return None
    m = re.match(r'^"(.*)"$', reply)
    return m.group(1) if m else None


def main():
    with open(INPUT_FILE) as f:
        examples = json.load(f)
    print(f"Translating {len(examples)} examples from {INPUT_FILE}\n")

    results = []
    for ex in examples:
        print(f"[{ex['id']}] translating...")
        predicted_fol = translate_to_fol(ex["evidence"], ex["hypothesis"])
        has_gold = "gold_fol" in ex
        results.append({
            "id": ex["id"],
            "hypothesis": ex["hypothesis"],
            "correct_label": ex["correct_label"],
            "gold_fol": "\n".join(ex["gold_fol"]) if has_gold else None,
            "predicted_fol": predicted_fol,
        })
        if has_gold:
            print("  gold:     ", " | ".join(ex["gold_fol"]))
        print("  predicted:", predicted_fol.replace("\n", " | "))
        print()

    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved comparisons to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

"""
PIPELINE B -- alternative to the FOL-intermediate approach (pipeline.py).

Here the LLM writes Narsese DIRECTLY -- no FOL stage, no mechanical
compiler. Correctness is instead checked by:
  1. Citation grounding (same mechanical substring check as Pipeline A)
  2. Fidelity check: back-translate the fact to English, and judge
     whether it accurately represents the EVIDENCE (not the hypothesis,
     and NOT the gold label -- checking against the gold answer here
     would leak it into generation, which wouldn't be a fair comparison
     against Pipeline A).
If either check fails, the model gets ONE retry on just that statement.

This lets us compare, on the same 20 examples: mechanical FOL compiler
(Pipeline A) vs. LLM-direct-to-Narsese with self-correction (Pipeline B).
"""

import re
from openai import OpenAI

client = OpenAI()

# Same structural examples as Pipeline A, but now in REAL Narsese directly
# -- no FOL intermediate representation at all.
FEW_SHOT_EXAMPLES = """
Example 1 (POSITIVE hypothesis; a chain: fact, then two implications):
Evidence: "The obligations and restrictions imposed by this Agreement will not apply to any information that: d. was independently developed by the Recipient without use of the Discloser's Confidential Information; or"
Hypothesis: "Receiving Party may independently develop information similar to Confidential Information."
Narsese:
POLARITY: POSITIVE
<(*, ReceivingParty, ConfidentialInfo) --> IndependentlyDeveloped>.
EVIDENCE: "was independently developed by the Recipient without use of the Discloser's Confidential Information"
<<(*, ReceivingParty, ConfidentialInfo) --> IndependentlyDeveloped> ==> <(*, ReceivingParty, ConfidentialInfo) --> Excluded>>.
EVIDENCE: "The obligations and restrictions imposed by this Agreement will not apply to any information that"
<<(*, ReceivingParty, ConfidentialInfo) --> Excluded> ==> <(*, ReceivingParty, ConfidentialInfo) --> Permitted>>.
EVIDENCE: "The obligations and restrictions imposed by this Agreement will not apply"
<(*, ReceivingParty, ConfidentialInfo) --> Permitted>?

Example 2 (POSITIVE hypothesis; fact + one implication):
Evidence: "The Parties will: a. limit disclosure of any Confidential Information to its directors, officers, employees, agents or representatives (collectively \\"Representatives\\") who have a need to know such Confidential Information in connection with the Transaction, and only for that purpose;"
Hypothesis: "Receiving Party may share some Confidential Information with some third-parties (including consultants, agents and professional advisors)."
Narsese:
POLARITY: POSITIVE
<(*, ThirdParty, ConfidentialInfo) --> Representative>.
EVIDENCE: "agents or representatives"
<<(*, ThirdParty, ConfidentialInfo) --> Representative> ==> <(*, ThirdParty, ConfidentialInfo) --> Permitted>>.
EVIDENCE: "limit disclosure of any Confidential Information to its directors, officers, employees, agents or representatives"
<(*, ThirdParty, ConfidentialInfo) --> Permitted>?

Example 3 (POSITIVE hypothesis, evidence says the OPPOSITE -- negative truth value):
Evidence: "Recipient will not disclose or permit access to Confidential Information to contract workers, consultants or contractors of Recipient or its Affiliates unless authorized by Disclosing Party in writing..."
Hypothesis: "Receiving Party may share some Confidential Information with some third-parties (including consultants, agents and professional advisors)."
Narsese:
POLARITY: POSITIVE
<(*, ContractWorker, ConfidentialInfo) --> Permitted>. %0.00;0.90%
EVIDENCE: "Recipient will not disclose or permit access to Confidential Information to contract workers, consultants or contractors"
<(*, ContractWorker, ConfidentialInfo) --> Permitted>?

Example 4 (NEGATIVE hypothesis -- "shall not"/"may not"/"must not" -- evidence CONFIRMS the prohibition):
Evidence: "Receiving Party shall not, and shall not permit any person to, reverse engineer any objects which embody Disclosing Party's Confidential Information."
Hypothesis: "Receiving Party shall not reverse engineer any objects which embody Disclosing Party's Confidential Information."
Narsese:
POLARITY: NEGATIVE
<(*, ReceivingParty, ReverseEngineer) --> Permitted>. %0.00;0.90%
EVIDENCE: "Receiving Party shall not, and shall not permit any person to, reverse engineer"
<(*, ReceivingParty, ReverseEngineer) --> Permitted>?

Example 5 (evidence is EMPTY -- contract never addresses this -- output ONLY polarity + query):
Evidence: ""
Hypothesis: "Receiving Party shall not use any Confidential Information for any purpose other than the purposes stated in Agreement."
Narsese:
POLARITY: NEGATIVE
<(*, ReceivingParty, OtherPurposeUse) --> Permitted>?
"""

SYSTEM_PROMPT = f"""You translate a contract clause (evidence) and a claim (hypothesis) DIRECTLY
into Narsese (NARS's formal reasoning language) -- NOT into intermediate First-Order Logic.
Follow EXACTLY the style shown in these examples.

Rules:
- The FIRST line must always be "POLARITY: POSITIVE" or "POLARITY: NEGATIVE" (NEGATIVE if the
  hypothesis itself is a prohibition: "shall not", "may not", "must not").
- Use product-term inheritance statements: <(*, Actor, Object) --> Predicate>.
  Negative facts get a truth-value tag: <(*, Actor, Object) --> Predicate>. %0.00;0.90%
  Implications connect two statements over the SAME product term:
  <<(*, Actor, Object) --> Pred1> ==> <(*, Actor, Object) --> Pred2>>.
- IMMEDIATELY after every asserted fact/implication line (never after the query), add:
  EVIDENCE: "<exact substring copied verbatim from Evidence>"
- Use THE SAME predicate name for the same underlying action everywhere it appears --
  inventing a different word for the same concept breaks the logical chain.
- Always end with exactly one query line: <(*, Actor, Object) --> Predicate>?
  Always phrase the query around the underlying POSITIVE action, never pre-negated.
- If evidence is empty, output ONLY the POLARITY line and the query line.
- Output ONLY the Narsese lines, nothing else -- no explanation, no markdown, no FOL.

{FEW_SHOT_EXAMPLES}
"""


def translate_direct(evidence, hypothesis):
    user_prompt = f'Evidence: "{evidence}"\nHypothesis: "{hypothesis}"\nNarsese:'
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    return response.choices[0].message.content.strip()


def parse_direct_output(raw_text):
    """Returns (polarity, fact_entries, query_line).
    fact_entries: list of {"statement": ..., "quote": ... or None}"""
    polarity = "POSITIVE"
    fact_entries = []
    query_line = None
    pending_statement = None

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.upper().startswith("POLARITY:"):
            value = line.split(":", 1)[1].strip().upper()
            if value in ("POSITIVE", "NEGATIVE"):
                polarity = value
            continue
        m = re.match(r'EVIDENCE:\s*"(.*)"\s*$', line)
        if m and pending_statement is not None:
            fact_entries[-1]["quote"] = m.group(1)
            pending_statement = None
            continue
        if line.endswith("?"):
            query_line = line
            pending_statement = None
            continue
        # otherwise: a fact/implication statement
        fact_entries.append({"statement": line, "quote": None})
        pending_statement = line

    return polarity, fact_entries, query_line


FIDELITY_BACK_TRANSLATE_PROMPT = """Translate this single Narsese statement into one plain English
sentence. If it has a truth-value tag like %0.00;0.90% near zero, phrase it as a NEGATIVE/false
claim. Output ONLY the sentence."""


def back_translate_fact(statement):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": FIDELITY_BACK_TRANSLATE_PROMPT},
            {"role": "user", "content": statement},
        ],
        temperature=0,
    )
    return response.choices[0].message.content.strip()


FIDELITY_JUDGE_PROMPT = """Evidence text: "{evidence}"
Claim to check: "{claim}"

Does the evidence text support this claim? This is a FIDELITY check (does the claim accurately
reflect what the evidence says), NOT a question about any hypothesis -- ignore any hypothesis.
Answer in this exact format:
VERDICT: MATCH or MISMATCH
REASON: one sentence"""


def judge_fidelity(evidence, back_translated_claim):
    prompt = FIDELITY_JUDGE_PROMPT.format(evidence=evidence, claim=back_translated_claim)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    reply = response.choices[0].message.content.strip()
    verdict = "MISMATCH"
    for line in reply.splitlines():
        if line.strip().upper().startswith("VERDICT:"):
            verdict = line.split(":", 1)[1].strip().upper()
    return verdict, reply


RETRY_SYSTEM_PROMPT = """You previously produced a Narsese statement and cited evidence for it, but
it failed a check: either the exact quote wasn't found in the real evidence, or the statement
doesn't faithfully represent what the evidence says.

You get ONE more chance. Look at the REAL evidence text very carefully.
- If it DOES support a fact about this topic, respond with a corrected Narsese statement line,
  then a new line "EVIDENCE: \\"<exact verbatim substring>\\"".
- If it does NOT, respond with exactly: NO_SUPPORT

Respond with ONLY the statement + EVIDENCE line, or exactly NO_SUPPORT."""


def retry_direct_statement(real_evidence_text, failed_statement, failed_quote, failure_reason):
    user_prompt = (
        f'Your previous statement: {failed_statement}\n'
        f'Your previous quote: "{failed_quote}"\n'
        f'Why it failed: {failure_reason}\n'
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
        return None, None
    lines = [l.strip() for l in reply.splitlines() if l.strip()]
    statement, quote = None, None
    for line in lines:
        m = re.match(r'EVIDENCE:\s*"(.*)"\s*$', line)
        if m:
            quote = m.group(1)
        else:
            statement = line
    return statement, quote

# NARS + LLM Contract Reasoning

Testing whether combining an LLM with NARS (a symbolic, non-axiomatic reasoning
engine) improves on a plain LLM's ability to read real NDAs and judge whether a
claim is **Entailed**, **Contradicted**, or **Not Mentioned**, using the
[ContractNLI](https://stanfordnlp.github.io/contract-nli/) dataset.

Built under Dr. Pei Wang, following the pipeline from Gabriel & Wang's
*"From Natural Language to Executable Narsese"*: `text → FOL → Narsese → run in ONA → label`,
applied here to real legal text rather than the paper's synthetic logic benchmark.

## Results

| Stage | Dataset | Result |
|---|---|---|
| Plain LLM baseline (no NARS) | 50 examples | 72% accuracy |
| Pipeline A, hand-curated gold set | 5 examples | 100% accuracy |
| Pipeline A, blind unseen set (before bug fixes) | 20 examples | 50% accuracy |
| Pipeline A, blind unseen set (after bug fixes) | 20 examples | **70% accuracy** |
| Pipeline B (direct-to-Narsese, no FOL compiler) | same 20 examples | 50% accuracy |

## Two pipelines, compared head to head

This repo contains two competing implementations, deliberately built to test
one specific design question: **does the FOL → Narsese step need to stay
mechanical (plain code), or can the LLM just write Narsese directly and
self-correct?**

- **Pipeline A** (`fol_translator.py` → `fol_to_narsese.py` → `run_ona.py`) —
  the LLM translates to FOL, a separate hand-written compiler (no AI) mechanically
  converts that FOL to Narsese, and ONA reasons over it.
- **Pipeline B** (`direct_translator_b.py` → `pipeline_b.py`) — the LLM writes
  Narsese directly, self-correcting via a back-translation fidelity check
  against the evidence.

**Finding:** Pipeline A outperforms Pipeline B (70% vs 50%) on identical data.
Digging into *why* — see [`compare_pipelines.py`](./compare_pipelines.py) output
and the write-up below — found that Pipeline B's LLM-based fidelity judge
rejected 6 of 8 flagged facts that were actually real and correctly cited,
while only 2 of 8 were genuine fabrications (the same 2 Pipeline A also caught).
**An LLM judging its own translation is noisier than a simple mechanical check.**
This is direct evidence for keeping the FOL→Narsese step mechanical, as the
original paper does.

## Citation grounding (catches hallucination)

Every fact either pipeline asserts must cite an exact quote from the real
contract evidence. That quote is mechanically verified as a real substring of
the evidence text — not just trusted. If it fails, the model gets one retry
with the real evidence shown explicitly; if it still fails, the fact is
dropped before it ever reaches the reasoner.

This caught two different contracts citing the *identical fabricated sentence*
— a generic NDA definition that doesn't appear in either contract — suggesting
the LLM was reciting memorized boilerplate rather than reading the document in
front of it. Both fabrications failed even on retry, with the real evidence
shown directly, ruling out simple misquoting as the explanation.

Note: accuracy did **not** improve from adding grounding, and that's expected —
grounding's job is turning *confidently wrong* (reasoning from a fabricated
fact) into *honestly uncertain* (correctly falling back to NotMentioned), not
raising the score. A flat accuracy number hides that improvement; see
`pipeline_results.json` for the per-example trace.

## Two real bugs found and fixed

**Polarity-blind label mapping** — the paper's fixed thresholds (frequency ≥
0.50 → True, ≤ 0.05 → False) assume the query mirrors the hypothesis directly.
For a prohibition hypothesis ("shall not X"), a correctly-derived low frequency
was being misread as Contradiction instead of Entailment. Fixed by tagging each
translation `POLARITY: POSITIVE/NEGATIVE` and flipping the label mapping
accordingly (`pipeline.py::label_from_frequency`).

**Silent partial-match in the compiler** — an unparseable FOL line was being
matched by a regex `re.match()` fallback that didn't require a full-line match,
silently producing a wrong, duplicated fact instead of correctly flagging the
line as unsupported. Fixed by requiring a full match (`fol_to_narsese.py`).

## Files

| File | What it does |
|---|---|
| `gold_examples.json` | 5 hand-translated examples, used as a reference/sanity check |
| `eval_batch1.json` | 20 blind, unseen ContractNLI examples (the real test) |
| `fol_translator.py` | Pipeline A: LLM translates evidence + hypothesis → FOL, with citations |
| `fol_to_narsese.py` | Pipeline A: mechanical, non-AI compiler, FOL → Narsese |
| `direct_translator_b.py` | Pipeline B: LLM translates directly to Narsese, self-corrects via fidelity check |
| `pipeline.py` | Runs Pipeline A end-to-end: translate → compile → ONA → label |
| `pipeline_b.py` | Runs Pipeline B end-to-end |
| `run_ona.py` | Feeds Narsese into a local ONA process and parses the result |
| `explain_answer.py` | Shows exactly which premises (and source quotes) ONA used for any conclusion |
| `back_translate.py` | Secondary validation: translates Narsese back to English, checks it still matches |
| `compare_pipelines.py` | Side-by-side comparison of Pipeline A vs B results |

## Running it

Requires [ONA](https://github.com/opennars/OpenNARS-for-Applications) installed
locally and an `OPENAI_API_KEY` set.

```bash
# Pipeline A
python3 fol_translator.py eval_batch1.json
python3 pipeline.py eval_batch1.json

# Pipeline B
python3 pipeline_b.py eval_batch1.json

# Compare
python3 compare_pipelines.py eval_batch1.json

# Inspect one answer's reasoning trace
python3 explain_answer.py eval_batch1_pipeline_results.json eval_14
```

## Known limitations / next steps

- The compiler only chains implications between statements sharing the same
  actor/object pair — it can't yet connect different entities (e.g. "if
  Discloser requests → Recipient must return").
- Fact and query sometimes use inconsistent predicate names, breaking the
  logical chain even when the right fact was correctly asserted.
- "Shall only include X" (an exclusivity claim) is currently misclassified as
  a simple prohibition — needs its own FOL pattern.
- "Permitted" (may) and "Obligated" (shall) are currently the same predicate —
  should be distinct.
- The 72% plain-LLM baseline was measured on a *different* 50 examples than
  the 20 used for Pipelines A/B — a fair, same-data three-way comparison
  (Pipeline C: plain LLM, no NARS, same 20 examples) is the next planned step.
- Only the pre-identified evidence span is translated, not the full contract —
  full-document retrieval is out of scope here.

# A3 — lossless NL → Narsese translation

**Goal:** no meaning of a contract sentence is silently lost on its way into ONA. A3 cannot promise a perfect
AI translation, so it does the next best thing: every word of the contract must be accounted for in some field of the
translation, and anything missing is reported by name and sent back for repair.

## What was wrong with A2 (and the old pipeline)
A2 forced every clause into 6 predicates × 15 fixed actions. Whatever did not fit — a second verb in a list, a recipient, a
purpose, "without retaining copies", the actor's real name, a long condition — was dropped. Actor names the model invented
("ListFusion", "VENDOR", "Investor") never matched the question, so the answer was "NotMentioned". Of the 17 misses on the
60-row set: 6 actor-name, 5 lost-verb/lost-action, 3 wrong modality, 1 clause wrongly called irrelevant, 2 retrieval misses
(the retrieved text never mentions the topic), and 1 ONA input-order bug. (ret_19 was both an order bug and, earlier, a translation row.)

## The format (open, nothing forced into a list)
Per statement: `force` (obligation / prohibition / permission / includes / excludes / survival / fact) + the exact modal words,
`agent` (controlled role + the contract's own name), one `act` per verb (free verb, object, recipient, purpose, manner, time,
place, source), `items` (what a definition includes/excludes, with technical / non_technical / oral_visual classes), free
`details` for anything else, nested `conditions` (only if) and `exceptions` (unless) with `any` / `all`, and the verbatim `quote`.
Full schema: top of `a3_core.py`. Hypothesis matching still goes through the 15 hypothesis actions via `maps_to`, but the
verb actually used is kept as well — `maps_to` is just the bridge.

## Checks (all mechanical unless noted)
1. **Ledger** – every content word of the passage must sit inside some field's verbatim text; leftover words are listed.
2. **Per-statement completeness** – a statement must carry the condition/limit words (if, unless, without, upon, only, not…) of its own quote.
3. **Grounding** – every quote/slot/ignored span must be a verbatim excerpt (list markers like (a), (ii), i) are skipped).
4. **Semantic audit** – modal wording vs force ("not be restricted", "not in breach", "do not apply" = permission), exception-vs-condition,
   "without X-ing" must have a prohibition, verb→hypothesis-action mapping vs a seed list, object-is-CI.
5. **Independent verifier (AI)** – a second call reads the deterministic English rendering and lists meaning that is missing / added / reversed.
6. **Repair** – flagged rows go back to the translator with the exact flag list (max 2 rounds; kept only if flags decrease).
7. **ONA robustness** – ONA's answer can depend on the order lines are fed in (one row gave NO answer in one order and the right one in another).
   The runner now tries 4 orders, uses any answer, and flags a disagreement.
Everything stays in a full knowledge base: `<input>_a3_kb/<id>.nal` (load it in ONA and ask anything).

## Policies you should check with the professor
- **Consent exceptions.** "…unless Raphael authorises" does NOT make copying permitted; "…except as required for the Transaction" DOES
  (an implied Permitted is derived). The gold labels disagree with this for ret_59 (same wording as ret_20 but opposite label), so at most one of the two can match.
- **Inferred statements** (e.g. "information from a third party is outside the definition" ⇒ may acquire it; "return all copies" ⇒ may not retain)
  are marked `inferred` and listed in the report for human confirmation.
- Only agent + canonical action + "object is the CI" + conditions/exceptions decide the verdict. Recipient/purpose/manner/time are in the knowledge base
  but do not gate the answer.

## Results (honest)
- 17 previously-missed rows, translated BY HAND into this format (drafts, written knowing the answers): 14/17 correct, 100% word coverage, 0 flags on correct translations.
  The 3 "wrong" are not translation errors: ret_10 and ret_45 (retrieval fetched an unrelated clause) and ret_59 (gold conflicts with ret_20).
  This shows the format can express the meaning; it does NOT yet show an AI will produce it.
- Checker test (`a3_mutation_test.py`): 110 deliberate damages to correct translations; 84% caught, 0 false alarms. The misses are almost all duplicated
  information (a recipient repeated in a sibling act, a condition repeated in another statement) and dropped *inferred* statements, which no word-count check can see —
  that is what the AI verifier is for.
- Plumbing check with a simulated lossy AI: it dropped the "without retaining copies" prohibition; the ledger flagged it and repair restored it.
- NOT done: a real run of the AI translator (needs your key), the other 43 rows, retrieval fixes.

## Run (Mac)
```
cd ~/Downloads/contract-nli
export OPENAI_API_KEY=...        # type your real key HERE, in your terminal only
python3 a3_run.py eval_ret_gold.json --translator llm --model gpt-4o
python3 a3_run.py eval17.json --translator gold --gold a3_gold.json     # no API: hand translations
python3 a3_mutation_test.py eval17.json a3_gold.json
```
Outputs: `*_a3_results.json`, `*_a3_report.md` (every statement in English + quote + flags + uncovered words), `*_a3_kb/`.

## Update: whole-meaning statements (after the first real run)
- **Hypotheses are no longer 3-word summaries.** `a3_hyp.py` spells out all 17 in full (e.g. nda-8 now carries the Disclosing Party, the
  "required by law, regulation or judicial process" trigger and "any Confidential Information"). The report prints this full meaning above
  the short name used for matching. DRAFT - professor to review.
- **Each act is one big Narsese statement** holding the role, the verb, the object and every filled slot, e.g.
  `<(*, ReceivingParty, notify, object_AnyRequest, recipient_Disclosers, manner_InWriting, time_Immediately) --> Obligated>`,
  with its conditions/exceptions as the antecedent and a bridge `<that statement ==> <(*, ReceivingParty, NotifyOnLegalDisclosure) --> Obligated>>`
  to the hypothesis action. Unmapped acts are in the knowledge base too.
- Tried feeding the separate detail layer (every item/condition frame) into ONA as well: ONA timed out (>60 s) on 17 rows, so it stays in
  the `.nal` files only (`--with-details` to try it). The runner now survives an ONA timeout.
- Re-test on the 17 hand-translated rows: still 14/17, 100% word coverage, and all four ONA input orders now agree on every row.

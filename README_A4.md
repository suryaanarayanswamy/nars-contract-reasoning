# A4: hypothesis-independent translation

**What changed.** The translator no longer sees the hypothesis and has no fixed action list.
Contract passages and the hypothesis go through the SAME prompt into the SAME open frame
(force, agent, acts with verb/object/slots, items, conditions, exceptions, verbatim quotes).
Nothing is tuned to the 17 NDA hypotheses, so a new dataset needs no new tables.

**Where contract and hypothesis meet.** One separate, logged step (`align`): for each contract unit it
returns same / kind_of / broader / outside / unrelated plus a one-line reason. It never edits the translation.
`transfers(relation, modality)` then decides which modalities carry over
(same: all; kind_of: Permitted/Obligated; broader: Prohibited; outside + OnlyIncludes: negated head).
Generic axioms AX1-AX5 (permitted vs prohibited vs obligated) replace the old hypothesis-specific axioms.

**Narsese carries the full meaning.** Every act is one tuple (role, verb, object, every filled slot, details);
the hypothesis query is its own full tuple, not a short summary. Conditions/exceptions are rule antecedents.

**Checks unchanged:** word ledger, per-statement completeness, grounding, semantic audit, independent verifier, repair loop.

**Results (hand translations + oracle aligner, i.e. the plumbing, not the AI):** 14/17 on the former misses, ret_5 correct.
Misses: ret_10, ret_45 (retrieval), ret_59 (gold conflict with ret_20; needs professor decision).
**Not yet tested:** the real AI translator and AI aligner (needs your key, typed in your terminal only).

Run: `export OPENAI_API_KEY=...` (terminal), `python3 a3_run.py eval_ret_recon.json --translator llm`

## Fixes after the first real AI run (eval_ret_recon, 60 rows)
- A statement was dropped whole when the AI left out a condition's name (ret_22 -> "No contract statements"). Now the name is derived from the condition's own words.
- A "fact" statement with no act (a plain definition) is no longer rejected (ret_3).
- Quotes the AI stitched together from separate places (ret_5, ret_30, ret_59) were flagged "ungrounded" and wiped the ledger to 0%. Now accepted if every word is in the passage, in order. The prompt also tells the AI to copy quotes contiguously.
- "Only includes" claims (ret_3, ret_7): any contract item broader than, outside, or unrelated to the claim now refutes it.
- The hypothesis condition term is short (it was a long concatenation of every alternative's text).
- Aligner prompt: judge the verb separately from the object; list of verbs are separate acts.
Known and unfixed: ret_8/ret_22 need an inferred permission ("may disclose if it became known from another source" implies acquiring it was allowed); ret_59 vs ret_20 policy conflict; ret_10/ret_45 retrieval.

## Fixes after the 2nd real run (46/60 = 77%; A2 was 43/60)
- Force word "means"/"defines"/"states"... is mapped to a valid force instead of rejecting (and losing) the whole statement (ret_33).
- Prompt: definitions/scope of the protected information are always `includes` statements (ret_28, ret_29, ret_33).
- Prompt: exclusions defined by what the recipient does/gets (independently developed, received from a third party) add an inferred permission for that activity (ret_1, 13, 22, 56); duties presupposing access (restrict access, require to sign) add an inferred permission to share (ret_32).
- Hypothesis gets one repair round when its own words are not all carried (ret_41).
- "Neither party shall be required to ..." recognised as an exemption.

## Conditions keep their OR / AND inside the Narsese (hypothesis question)
`cond_term()` writes a condition as `(||, <(*,Role,AtomA) --> Holds>, <(*,Role,AtomB) --> Holds>)` (any) or `(&&, ...)` (all) inside the question tuple, instead of one long concatenated word.

## Multi-agent check and fresh-data comparison (21 Oct)
**Multi-agent (`a3_multi.py`)**: N agents (default 3), each with a different point of view (standard / careful lawyer / formal logician) run the WHOLE pipeline
(translate contract + claim, checks, repair, implied-permission pass, alignment, ONA). The label is decided by vote (tie: highest ONA confidence);
rows where agents disagree are listed for review. `python3 a3_multi.py FILE --agents 3`. `--self-test` checks the voting logic without AI.

**Fresh test set (`eval_fresh60.json`)**: 60 rows (20 per label) from 52 ContractNLI test/dev documents that none of the 60 development rows came from.
Entailment/Contradiction rows carry the gold evidence spans; NotMentioned rows carry the 2 most lexically similar spans of the same document (hard negatives), or none.
Gold evidence isolates translation + reasoning from retrieval.

**Baseline (`a3_baseline.py`)**: the same model gets the same hypothesis and evidence and answers directly. `a3_compare.py` prints both side by side.

## IMPORTANT: ONA limits found on 22 Oct (affects all earlier ONA results)
1. ONA keeps only the first TWO parts of any compound: (*, a, b, c) is read as (a * b); (&&, A, B, C) as (A && B). Fixed: all products/conjunctions/disjunctions are written as BALANCED binary pairs; inner conjunctions are asserted as assumptions (lenient mode).
2. ONA stores a term as a binary tree in a fixed array (64 slots by default). Larger statements are SILENTLY DROPPED. Fixed: balanced trees need only log2(n) levels, and `patch_ona.sh` builds ONA with larger limits and smoke-tests each build. On macOS (arm64) a 256-slot build compiles but does not start (dyld cannot map it), so 128/1023 is the ceiling there; the encoding was made shallower to fit.
3. Names longer than 31 characters are cut by ONA (collisions possible). Fixed: names above 31 characters get a stable short form (prefix + hash) when fed to ONA.
4. `a2_ona.run` now reports `dropped` (statements fed but not echoed) and a3_run flags `ona_dropped_lines`; a start-up check warns if the ONA build is too small.
Also: slot terms keep "OtherThan" when the slot text says "other than / except"; "must use ONLY for X" is treated as a prohibition of every other use.
Hand-translation regression with the bigger build: 14/17 (unchanged). Earlier AI-run numbers (46/60, 49/60, fresh15) were produced with the small build and must be re-measured.

## Changes 23-26 Oct (a4.2)
- `a2_ona.run` raises on a real crash (exit code, stderr) instead of returning "no answer"; ONA's own assertion (exit code 1, e.g. "COMPOUND_TERM_SIZE_MAX too small") returns no answer with an `error` field and a3_run flags `ona_error`.
- Condition leaves are `<Role_Atom --> Holds>` (one level shallower). A deep AND/OR condition inside the hypothesis is named by a condition atom `<Role_whenOr... --> Holds>` and its full structure is kept in a definition line (`hypothesis_logic["defs"]`, listed in the `axioms` of the results).
- Several alternative conditions are named once (`AnyOf_...`) and every conclusion uses that name (112 lines down to 54 on ret_16). Knowledge bases above 40 lines run 10 cycles instead of 50 (answers are stable) and the ONA timeout scales with size.
- "Excludes" clauses ("does not include X") are now units: they deny "includes", assert "excludes", and (policy, to be confirmed) imply a permission for an aligned hypothesis act.
- New alignment relation `conflicts` (an obligation incompatible with the hypothesis act, e.g. "must return or destroy" vs "may retain"): denies the permission.
- dev15 (14 rows) with the AI translator: 8/14. The hand-translation regression stays at 14/17. Alignment labels are not stable across prompt versions (ret_8, ret_11 flipped), see the multi-agent test.
- `translation_check_sheet.xlsx`: human check of translation quality (34 clauses, 14 hypotheses).

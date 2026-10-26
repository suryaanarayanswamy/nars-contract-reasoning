"""Alignment: the ONLY step where a contract statement and the hypothesis are looked at together, and it outputs nothing but a
relation label per statement (logged in the report). The translator never sees the hypothesis.

OracleAligner  = test scaffolding: reads the hand labels written into the gold translations (NOT an AI, NOT for real runs).
LLM aligner    = LLMTranslator.align in a3_translate.py.
"""
import a2_vocab as V
import a3_core as K

CI_OBJECT_ACTIONS = {"UseForOtherPurposes", "ShareWithEmployees", "ShareWithThirdParties", "ReverseEngineer", "ReturnOrDestroy",
                     "CreateCopy", "RetainCopies", "DiscloseUnderLegalProcess", "MarkConfidentialInfo"}


class OracleAligner:
    def align(self, ex, hyp_stmt, hyp, units, stmts):
        hit = V.lookup_hypothesis(ex["hypothesis"])
        action = hit[3] if hit else None
        out = []
        for u in units:
            s = stmts[u["stmt"]]
            if u["kind"] == "act":
                a = s["acts"][u["act"]]
                ok = a["maps_to"] == action and (a["object"]["is_ci"] or action not in CI_OBJECT_ACTIONS)
                out.append((a["relation"] if ok else "unrelated", "oracle: hand label"))
            elif u["kind"] == "item":
                cls = [K.CLASS_ITEM[c] for c in s["items"][u["item"]]["classes"]]
                if action == "TechnicalInfo":
                    rel = "outside" if "NonTechnicalInfo" in cls else ("same" if cls == ["TechnicalInfo"] else "unrelated")
                elif action == "VerbalInfo":
                    rel = "same" if cls == ["VerbalInfo"] else ("broader" if "VerbalInfo" in cls else "unrelated")
                else:
                    rel = "unrelated"
                out.append((rel, "oracle: hand label"))
            else:
                out.append(("same" if action == "Termination" else "unrelated", "oracle: hand label"))
        return out

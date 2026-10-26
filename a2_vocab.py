"""
A2 vocabulary: the fixed set of logical predicates, canonical actions,
hypothesis encodings and background rules (axioms) the pipeline uses.

Why a fixed vocabulary: in the first version the AI invented a new action
name for the hypothesis and for the contract, so the two never connected
(or, worse, the AI copied the hypothesis into the facts). Here the contract
translator must pick from the SAME canonical actions the hypotheses use, so
a match (or a conflict) between a contract statement and a hypothesis is
decided by the reasoner, not by the translator.
"""
import re

# ---- the six relations a statement can express --------------------------------
PREDICATES = ("Obligated", "Prohibited", "Permitted", "Includes", "OnlyIncludes", "Survives")

# ---- canonical actions (one per ContractNLI hypothesis) ------------------------
# name -> (default actor, plain-English gloss shown to the translator)
ACTIONS = {
    "MarkConfidentialInfo":     ("DisclosingParty", "expressly mark or identify information as confidential"),
    "UseForOtherPurposes":      ("ReceivingParty",  "use Confidential Information for any purpose other than the purposes the Agreement states"),
    "ShareWithEmployees":       ("ReceivingParty",  "share/disclose Confidential Information with the Receiving Party's own employees"),
    "ShareWithThirdParties":    ("ReceivingParty",  "share/disclose Confidential Information with third parties (consultants, agents, advisors, representatives, contractors)"),
    "NotifyOnLegalDisclosure":  ("ReceivingParty",  "notify the Disclosing Party when required by law/court/regulator to disclose"),
    "DiscloseAgreementExistence": ("ReceivingParty", "disclose that the Agreement exists or was negotiated"),
    "ReverseEngineer":          ("ReceivingParty",  "reverse engineer, disassemble or decompile objects embodying Confidential Information"),
    "IndependentlyDevelop":     ("ReceivingParty",  "independently develop information similar to Confidential Information"),
    "AcquireFromThirdParty":    ("ReceivingParty",  "acquire information similar to Confidential Information from a third party"),
    "GrantRights":              ("Agreement",       "grant the Receiving Party any right/licence to Confidential Information (actor is the Agreement)"),
    "ReturnOrDestroy":          ("ReceivingParty",  "return or destroy Confidential Information (e.g. on termination or request)"),
    "CreateCopy":               ("ReceivingParty",  "make or keep a copy of Confidential Information"),
    "RetainCopies":             ("ReceivingParty",  "keep Confidential Information after return or destruction"),
    "SolicitRepresentatives":   ("ReceivingParty",  "solicit the Disclosing Party's employees/representatives"),
    "DiscloseUnderLegalProcess": ("ReceivingParty", "disclose Confidential Information to a court, regulator or authority because law/court order/subpoena requires it (NOT sharing with third parties)"),
}

# Items used with Includes / OnlyIncludes (actor = the category, e.g. ConfidentialInfo)
ITEMS = {
    "TechnicalInfo":    "technical or scientific information (designs, source code, processes, formulas...)",
    "NonTechnicalInfo": "anything that is not technical: business, financial, marketing, customer, personnel information, "
                        "or information of ANY kind ('any data or information', 'whatever its nature')",
    "VerbalInfo":       "oral, verbal or visual information",
}
ITEM_ALIASES = {
    "businessinfo": "NonTechnicalInfo", "financialinfo": "NonTechnicalInfo", "marketinginfo": "NonTechnicalInfo",
    "customerinfo": "NonTechnicalInfo", "personnelinfo": "NonTechnicalInfo", "businessinformation": "NonTechnicalInfo",
    "technicalinformation": "TechnicalInfo", "oralinfo": "VerbalInfo", "oralinformation": "VerbalInfo",
    "verbalinformation": "VerbalInfo", "visualinfo": "VerbalInfo",
}

# ---- the 17 ContractNLI hypotheses, encoded once and checked by hand -----------
# id -> (text, predicate, actor, action)
HYPOTHESES = {
    "nda-1":  ("All Confidential Information shall be expressly identified by the Disclosing Party.", "Obligated", "DisclosingParty", "MarkConfidentialInfo"),
    "nda-2":  ("Confidential Information shall only include technical information.", "OnlyIncludes", "ConfidentialInfo", "TechnicalInfo"),
    "nda-3":  ("Confidential Information may include verbally conveyed information.", "Includes", "ConfidentialInfo", "VerbalInfo"),
    "nda-4":  ("Receiving Party shall not use any Confidential Information for any purpose other than the purposes stated in Agreement.", "Prohibited", "ReceivingParty", "UseForOtherPurposes"),
    "nda-5":  ("Receiving Party may share some Confidential Information with some of Receiving Party's employees.", "Permitted", "ReceivingParty", "ShareWithEmployees"),
    "nda-7":  ("Receiving Party may share some Confidential Information with some third-parties (including consultants, agents and professional advisors).", "Permitted", "ReceivingParty", "ShareWithThirdParties"),
    "nda-8":  ("Receiving Party shall notify Disclosing Party in case Receiving Party is required by law, regulation or judicial process to disclose any Confidential Information.", "Obligated", "ReceivingParty", "NotifyOnLegalDisclosure"),
    "nda-10": ("Receiving Party shall not disclose the fact that Agreement was agreed or negotiated.", "Prohibited", "ReceivingParty", "DiscloseAgreementExistence"),
    "nda-11": ("Receiving Party shall not reverse engineer any objects which embody Disclosing Party's Confidential Information.", "Prohibited", "ReceivingParty", "ReverseEngineer"),
    "nda-12": ("Receiving Party may independently develop information similar to Confidential Information.", "Permitted", "ReceivingParty", "IndependentlyDevelop"),
    "nda-13": ("Receiving Party may acquire information similar to Confidential Information from a third party.", "Permitted", "ReceivingParty", "AcquireFromThirdParty"),
    "nda-15": ("Agreement shall not grant Receiving Party any right to Confidential Information.", "Prohibited", "Agreement", "GrantRights"),
    "nda-16": ("Receiving Party shall destroy or return some Confidential Information upon the termination of Agreement.", "Obligated", "ReceivingParty", "ReturnOrDestroy"),
    "nda-17": ("Receiving Party may create a copy of some Confidential Information in some circumstances.", "Permitted", "ReceivingParty", "CreateCopy"),
    "nda-18": ("Receiving Party shall not solicit some of Disclosing Party's representatives.", "Prohibited", "ReceivingParty", "SolicitRepresentatives"),
    "nda-19": ("Some obligations of Agreement may survive termination of Agreement.", "Survives", "Obligations", "Termination"),
    "nda-20": ("Receiving Party may retain some Confidential Information even after the return or destruction of Confidential Information.", "Permitted", "ReceivingParty", "RetainCopies"),
}


def _key(text):
    return re.sub(r"\s+", " ", text.strip().lower())

HYPOTHESIS_BY_TEXT = {_key(v[0]): (k,) + v[1:] for k, v in HYPOTHESES.items()}


def lookup_hypothesis(text):
    """Return (id, pred, actor, action) for one of the 17 known hypotheses, else None."""
    return HYPOTHESIS_BY_TEXT.get(_key(text))


# ---- background rules, written once by hand ------------------------------------
# These are the ONLY places where "reasoning" beyond matching happens.
T = lambda a, x, p: f"<(*, {a}, {x}) --> {p}>"
AXIOMS = [
    ("AX1", "If an action is permitted, it is not prohibited.",
     f"<{T('$a','$x','Permitted')} ==> (--, {T('$a','$x','Prohibited')})>."),
    ("AX2", "If an action is prohibited, it is not permitted.",
     f"<{T('$a','$x','Prohibited')} ==> (--, {T('$a','$x','Permitted')})>."),
    ("AX3", "If an action is obligatory, it is permitted.",
     f"<{T('$a','$x','Obligated')} ==> {T('$a','$x','Permitted')}>."),
    ("AX4", "If an action is obligatory, it is not prohibited.",
     f"<{T('$a','$x','Obligated')} ==> (--, {T('$a','$x','Prohibited')})>."),
    ("AX5", "If an action is prohibited, it is not obligatory.",
     f"<{T('$a','$x','Prohibited')} ==> (--, {T('$a','$x','Obligated')})>."),
    ("AX6", "If a category includes non-technical items, it does not ONLY include technical ones.",
     f"<{T('$c','NonTechnicalInfo','Includes')} ==> (--, {T('$c','TechnicalInfo','OnlyIncludes')})>."),
]

# rule added after batch-2 analysis: keeping a copy after return is itself having a copy
AXIOMS.append(("AX7", "If keeping a copy after return/destruction is permitted, having a copy is permitted.",
               f"<{T('$a','RetainCopies','Permitted')} ==> {T('$a','CreateCopy','Permitted')}>."))

# ---- mechanical sanity data used by the audit -----------------------------------
# words that should appear in the quote (or its condition texts) for the AI to claim this canonical action
ACTION_CUES = {
    "MarkConfidentialInfo": r"mark|identif|label|designat|stamp|legend|however disclosed|whether or not|oral",
    "UseForOtherPurposes": r"use|purpose|misuse|sole|limited|manufactur|test",
    "ShareWithEmployees": r"employee|director|officer|disclos|shar|personnel|staff|representative|need to know|person",
    "ShareWithThirdParties": r"third|consultant|agent|advis|representative|contractor|disclos|shar|transfer|any party|any person|affiliate|access",
    "NotifyOnLegalDisclosure": r"notif|inform|advis|notice|prompt",
    "DiscloseAgreementExistence": r"exist|negotiat|fact|agreement|terms|discussion|transaction",
    "ReverseEngineer": r"reverse|disassembl|decompil|analy",
    "IndependentlyDevelop": r"independent|develop|without use",
    "AcquireFromThirdParty": r"third party|receiv|acquir|obtain|rightful",
    "GrantRights": r"right|licen|grant|ownership|title",
    "ReturnOrDestroy": r"return|destr|redeliver|certif|delet|erase|surrender",
    "CreateCopy": r"cop|reproduc|duplicat|retain|archiv|back-up|backup",
    "RetainCopies": r"retain|keep|cop|archiv|back-up|backup|record",
    "SolicitRepresentatives": r"solicit|hire|employ|recruit|induce|entice",
    "DiscloseUnderLegalProcess": r"law|court|order|subpoena|regulat|judicial|governmental|legal|exchange|supervis|authorit",
}
# predicates that make sense for each canonical action (anything else is flagged for review)
_P, _O, _M = "Permitted", "Obligated", "Prohibited"
ACTION_PREDS = {
    "MarkConfidentialInfo": {_O, _M, _P}, "UseForOtherPurposes": {_M, _P}, "ShareWithEmployees": {_P, _M},
    "ShareWithThirdParties": {_P, _M}, "NotifyOnLegalDisclosure": {_O, _P}, "DiscloseAgreementExistence": {_M, _P},
    "ReverseEngineer": {_M, _P}, "IndependentlyDevelop": {_P, _M}, "AcquireFromThirdParty": {_P, _M},
    "GrantRights": {_M, _P}, "ReturnOrDestroy": {_O, _P}, "CreateCopy": {_P, _M}, "RetainCopies": {_P, _M},
    "SolicitRepresentatives": {_M, _P}, "DiscloseUnderLegalProcess": {_P, _M},
}

# words that CONTRADICT a canonical action (e.g. disclosure to a court is not "sharing with third parties")
ACTION_ANTICUES = {
    "UseForOtherPurposes": r"required to be disclosed|required by law|stock exchange|subpoena|court order|regulatory (body|authority|request)|governmental",
    "ShareWithThirdParties": r"governmental|court|subpoena|judicial|regulator|administrative order|required by law|legal process",
    "ShareWithEmployees": r"governmental|court|subpoena|judicial|regulator|administrative order|required by law",
    "MarkConfidentialInfo": r"hold such|subject to the terms|receive and hold",
}

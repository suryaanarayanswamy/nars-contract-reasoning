"""Hand-written translations of the 17 ContractNLI hypotheses in the SAME open format the contract uses (DRAFTS for professor review).
For a new dataset the AI translates its hypotheses with the same prompt - this file is only so the test runs without an API key."""
import json
from make_gold3 import S, A, O, I, L, D

def H(text, force, ft, role, name, acts=None, **kw): return S(text.rstrip("."), force, ft, role, name, acts, **kw)
RP = ("ReceivingParty", "Receiving Party")
G = {
 "nda-1": H("All Confidential Information shall be expressly identified by the Disclosing Party.", "obligation", "shall be", "DisclosingParty", "the Disclosing Party",
            [A("identify", "identified", obj=O("All Confidential Information"), manner=("expressly", "Expressly"))]),
 "nda-2": H("Confidential Information shall only include technical information.", "includes", "shall only include", "ConfidentialInfo", "Confidential Information",
            items=[I("technical information", "TechnicalInformation")], exh=True),
 "nda-3": H("Confidential Information may include verbally conveyed information.", "includes", "may include", "ConfidentialInfo", "Confidential Information",
            items=[I("verbally conveyed information", "VerballyConveyedInformation")]),
 "nda-4": H("Receiving Party shall not use any Confidential Information for any purpose other than the purposes stated in Agreement.", "prohibition", "shall not", *RP,
            [A("use", "use", obj=O("any Confidential Information"), purpose=("for any purpose other than the purposes stated in Agreement", "OtherThanStatedPurposes"))]),
 "nda-5": H("Receiving Party may share some Confidential Information with some of Receiving Party's employees.", "permission", "may", *RP,
            [A("share", "share", obj=O("some Confidential Information"), recipient=("with some of Receiving Party's employees", "ReceivingPartyEmployees"))]),
 "nda-7": H("Receiving Party may share some Confidential Information with some third-parties (including consultants, agents and professional advisors).", "permission", "may", *RP,
            [A("share", "share", obj=O("some Confidential Information"), recipient=("with some third-parties (including consultants, agents and professional advisors)", "ThirdPartiesIncludingAdvisors"))]),
 "nda-8": H("Receiving Party shall notify Disclosing Party in case Receiving Party is required by law, regulation or judicial process to disclose any Confidential Information.", "obligation", "shall", *RP,
            [A("notify", "notify", recipient=("Disclosing Party", "DisclosingParty"))],
            cond=[L("RequiredToDisclose", "in case Receiving Party is required by law, regulation or judicial process to disclose any Confidential Information")]),
 "nda-10": H("Receiving Party shall not disclose the fact that Agreement was agreed or negotiated.", "prohibition", "shall not", *RP,
             [A("disclose", "disclose", obj=O("the fact that Agreement was agreed or negotiated"))]),
 "nda-11": H("Receiving Party shall not reverse engineer any objects which embody Disclosing Party's Confidential Information.", "prohibition", "shall not", *RP,
             [A("reverse_engineer", "reverse engineer", obj=O("any objects which embody Disclosing Party's Confidential Information"))]),
 "nda-12": H("Receiving Party may independently develop information similar to Confidential Information.", "permission", "may", *RP,
             [A("develop", "develop", obj=O("information similar to Confidential Information"), manner=("independently", "Independently"))]),
 "nda-13": H("Receiving Party may acquire information similar to Confidential Information from a third party.", "permission", "may", *RP,
             [A("acquire", "acquire", obj=O("information similar to Confidential Information"), source=("from a third party", "ThirdParty"))]),
 "nda-15": H("Agreement shall not grant Receiving Party any right to Confidential Information.", "prohibition", "shall not", "Agreement", "Agreement",
             [A("grant", "grant", obj=O("any right to Confidential Information"), recipient=("Receiving Party", "ReceivingParty"))]),
 "nda-16": H("Receiving Party shall destroy or return some Confidential Information upon the termination of Agreement.", "obligation", "shall", *RP,
             [A("destroy_or_return", "destroy or return", obj=O("some Confidential Information"), time=("upon the termination of Agreement", "UponTermination"))]),
 "nda-17": H("Receiving Party may create a copy of some Confidential Information in some circumstances.", "permission", "may", *RP,
             [A("create", "create", obj=O("a copy of some Confidential Information"))], details=[D("circumstance", "in some circumstances")]),
 "nda-18": H("Receiving Party shall not solicit some of Disclosing Party's representatives.", "prohibition", "shall not", *RP,
             [A("solicit", "solicit", obj=O("some of Disclosing Party's representatives"))]),
 "nda-19": H("Some obligations of Agreement may survive termination of Agreement.", "survival", "may survive", "Obligations", "Some obligations of Agreement",
             details=[D("event", "termination of Agreement")]),
 "nda-20": H("Receiving Party may retain some Confidential Information even after the return or destruction of Confidential Information.", "permission", "may", *RP,
             [A("retain", "retain", obj=O("some Confidential Information"), time=("even after the return or destruction of Confidential Information", "AfterReturnOrDestruction"))]),
}
json.dump(G, open("a3_hyp_gold.json", "w"), indent=1)
print("wrote a3_hyp_gold.json", len(G))

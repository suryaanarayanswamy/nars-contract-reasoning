"""Hand-written A3 translations (DRAFTS for professor review) of the 17 rows A2 got wrong on eval_ret_gold.
They test the representation, compiler, ledger and ONA end to end. They are NOT the AI's output."""
import json

def O(text, ci=False): return {"text": text, "is_ci": ci}
def I(text, term, *classes): return {"text": text, "term": term, "classes": list(classes)}
def D(slot, text): return {"slot": slot, "text": text}
def L(atom, text, **frame): return {"atom": atom, "text": text, **({"frame": frame} if frame else {})}
def ANY(text, *kids): return {"text": text, "any": list(kids)}
def ALL(text, *kids): return {"text": text, "all": list(kids)}
def A(verb, vt, maps=None, rel="same", obj=None, **slots):
    return {"verb": verb, "verb_text": vt, "maps_to": maps, "relation": rel, "object": obj or O(""),
            "slots": {k: {"text": v[0], "term": v[1]} for k, v in slots.items()}}
def S(quote, force, ft, role, name, acts=None, items=None, cond=None, exc=None, exh=False, details=None, inferred=False):
    return {"quote": quote, "force": force, "force_text": ft, "agent": {"role": role, "name": name},
            "acts": acts or [], "items": items or [], "conditions": cond or [], "exceptions": exc or [],
            "exhaustive": exh, "details": details or [], "inferred": inferred}

G = {}

# ------------------------------------------------------------------ ret_3
G["ret_3"] = {"statements": [
    S("The Parties acknowledge that each owns certain CONFIDENTIAL INFORMATION, as defined herein", "fact", "acknowledge",
      "BothParties", "The Parties", [A("own", "owns", obj=O("certain CONFIDENTIAL INFORMATION", True))],
      details=[D("definition", "as defined herein")]),
    S("which might relate to the inventions, conceptions, ideas, know-how, discoveries, processes, machines, manufactures, compositions of matter, formulations, processes, biological material, biological methods, or any improvements thereof, whether or not patentable or suitable for other form of exclusive right or legal protection, conceived, made or derived during the course of Work within the Project under this JRA",
      "includes", "might relate to", "ConfidentialInfo", "CONFIDENTIAL INFORMATION",
      items=[I("inventions", "Inventions", "technical"), I("conceptions", "Conceptions", "technical"), I("ideas", "Ideas", "technical"),
             I("know-how", "KnowHow", "technical"), I("discoveries", "Discoveries", "technical"), I("processes", "Processes", "technical"),
             I("machines", "Machines", "technical"), I("manufactures", "Manufactures", "technical"),
             I("compositions of matter", "CompositionsOfMatter", "technical"), I("formulations", "Formulations", "technical"),
             I("biological material", "BiologicalMaterial", "technical"), I("biological methods", "BiologicalMethods", "technical"),
             I("any improvements thereof", "Improvements", "technical")],
      details=[D("scope", "whether or not patentable or suitable for other form of exclusive right or legal protection"),
               D("origin", "conceived, made or derived during the course of Work within the Project under this JRA")]),
    S("\"CONFIDENTIAL INFORMATION\" as used in this Agreement means all technical or business information disclosed by one of the Parties to another pursuant to the JRA that is identified at the time of disclosure or within thirty (30) days thereafter as being confidential and proprietary",
      "includes", "means", "ConfidentialInfo", "CONFIDENTIAL INFORMATION",
      items=[I("technical", "Technical", "technical"), I("business information", "Business", "non_technical")], exh=True,
      details=[D("scope", "as used in this Agreement"), D("disclosure", "disclosed by one of the Parties to another pursuant to the JRA")],
      cond=[L("IdentifiedConfidential", "that is identified at the time of disclosure or within thirty (30) days thereafter as being confidential and proprietary",
              verb="identify", object="information")]),
]}

# ------------------------------------------------------------------ ret_8
Q8 = "Receiver may disclose Confidential Information if the same: (d) becomes known to Receiver on a non-confidential basis from a source other than VIDAR without breach of this Agreement by Receiver"
C8 = L("KnownFromOtherSource", "if the same: (d) becomes known to Receiver on a non-confidential basis from a source other than VIDAR without breach of this Agreement by Receiver",
       verb="become_known", object="Confidential Information")
G["ret_8"] = {"statements": [
    S(Q8, "permission", "may", "ReceivingParty", "Receiver", [A("disclose", "disclose", obj=O("Confidential Information", True))], cond=[C8]),
    S("becomes known to Receiver on a non-confidential basis from a source other than VIDAR without breach of this Agreement by Receiver", "permission", "may", "ReceivingParty", "Receiver",
      [A("acquire", "becomes known", "AcquireFromThirdParty", obj=O("Confidential Information", True),
         source=("from a source other than VIDAR", "OtherSource"), manner=("on a non-confidential basis", "NonConfidential"))],
      details=[D("lawfulness", "without breach of this Agreement by Receiver")], inferred=True),
]}

# ------------------------------------------------------------------ ret_10 (retrieval miss: the text is about something else)
G["ret_10"] = {"statements": [
    S("Receiving Party shall hold and maintain the Sensitive Information in strictest confidence for the sole and exclusive benefit of the Disclosing Party",
      "obligation", "shall", "ReceivingParty", "Receiving Party",
      [A("hold", "hold", obj=O("the Sensitive Information", True), manner=("in strictest confidence", "StrictestConfidence"),
         purpose=("for the sole and exclusive benefit of the Disclosing Party", "BenefitOfDiscloser")),
       A("maintain", "maintain", obj=O("the Sensitive Information", True), manner=("in strictest confidence", "StrictestConfidence"),
         purpose=("for the sole and exclusive benefit of the Disclosing Party", "BenefitOfDiscloser"))])]}

# ------------------------------------------------------------------ ret_15
AUTH15 = L("RaphaelWrittenAuthorization", "without the written authorization by Raphael", agent="Raphael", verb="authorize")
G["ret_15"] = {"statements": [
    S("ListFusion will not use any 3rd party agents, vendors, or other providers to process the List without the written authorization by Raphael",
      "prohibition", "will not", "ReceivingParty", "ListFusion",
      [A("allow_processing", "use", "ShareWithThirdParties", obj=O("the List", True),
         recipient=("any 3rd party agents, vendors, or other providers", "ThirdPartyProviders"), purpose=("to process the List", "ProcessList"))],
      exc=[AUTH15], inferred=True),
    S("ListFusion will not create, generate, distribute, or convey to any 3rd party a username or password without prior written authorization by Raphael",
      "prohibition", "will not", "ReceivingParty", "ListFusion",
      [A("create", "create", obj=O("a username or password")), A("generate", "generate", obj=O("a username or password")),
       A("distribute", "distribute", obj=O("a username or password"), recipient=("to any 3rd party", "ThirdParty")),
       A("convey", "convey", obj=O("a username or password"), recipient=("to any 3rd party", "ThirdParty"))],
      exc=[L("RaphaelPriorWrittenAuthorization", "without prior written authorization by Raphael", agent="Raphael", verb="authorize")]),
]}

# ------------------------------------------------------------------ ret_19
G["ret_19"] = {"statements": [
    S("The List will not be reproduced, transferred, or conveyed to any 3rd party without prior written authorization by Raphael",
      "prohibition", "will not be", "ReceivingParty", "",
      [A("reproduce", "reproduced", "CreateCopy", obj=O("The List", True)),
       A("transfer", "transferred", "ShareWithThirdParties", obj=O("The List", True), recipient=("to any 3rd party", "ThirdParty")),
       A("convey", "conveyed", "ShareWithThirdParties", obj=O("The List", True), recipient=("to any 3rd party", "ThirdParty"))],
      exc=[L("RaphaelPriorWrittenAuthorization", "without prior written authorization by Raphael", agent="Raphael", verb="authorize")]),
    S("Additionally, ListFusion. agrees not to copy, reprint or disseminate the publications, or any information concerning the publication including the articles, graphics or contents without express written authorization from Raphael",
      "prohibition", "agrees not to", "ReceivingParty", "ListFusion",
      [A("copy", "copy", "CreateCopy", obj=O("the publications, or any information concerning the publication including the articles, graphics or contents", True)),
       A("reprint", "reprint", "CreateCopy", obj=O("the publications, or any information concerning the publication including the articles, graphics or contents", True)),
       A("disseminate", "disseminate", "ShareWithThirdParties", obj=O("the publications, or any information concerning the publication including the articles, graphics or contents", True))],
      details=[D("connective", "Additionally")],
      exc=[L("RaphaelExpressWrittenAuthorization", "without express written authorization from Raphael", agent="Raphael", verb="authorize")]),
]}

# ------------------------------------------------------------------ ret_20
G["ret_20"] = {"statements": [
    S("Confidential Information shall not be reproduced in any form except as required to accomplish the intent of this Agreement",
      "prohibition", "shall not be", "ReceivingParty", "",
      [A("reproduce", "reproduced", "CreateCopy", obj=O("Confidential Information", True), manner=("in any form", "AnyForm"))],
      exc=[L("RequiredForIntent", "except as required to accomplish the intent of this Agreement", verb="require", object="reproduction")])]}

# ------------------------------------------------------------------ ret_24
REQ24 = L("CompanyRequest", "Upon the Company's request", agent="Company", verb="request")
G["ret_24"] = {"statements": [
    S("Upon the Company's request, you shall promptly deliver to the Company or destroy all written Evaluation Materials and any other written materials",
      "obligation", "shall", "ReceivingParty", "you",
      [A("deliver", "deliver", "ReturnOrDestroy", obj=O("all written Evaluation Materials and any other written materials", True),
         recipient=("to the Company", "Company"), time=("promptly", "Promptly")),
       A("destroy", "destroy", "ReturnOrDestroy", obj=O("all written Evaluation Materials and any other written materials", True), time=("promptly", "Promptly"))],
      cond=[REQ24]),
    S("without retaining, in whole or in part, any copies, extracts or other reproductions (whatever the form or storage medium) of such materials",
      "prohibition", "without retaining", "ReceivingParty", "you",
      [A("retain", "retaining", "RetainCopies", obj=O("any copies, extracts or other reproductions", True),
         manner=("in whole or in part", "InWholeOrPart"))],
      details=[D("scope", "whatever the form or storage medium"), D("of_what", "of such materials")], cond=[REQ24]),
    S("and shall certify the destruction of such materials in writing to the Company", "obligation", "shall", "ReceivingParty", "",
      [A("certify", "certify", obj=O("the destruction of such materials"), manner=("in writing", "InWriting"), recipient=("to the Company", "Company"))],
      cond=[REQ24]),
]}

# ------------------------------------------------------------------ ret_25
G["ret_25"] = {"statements": [
    S("neither Party will be restricted from using the information contained in the Evaluation Material that is retained in the minds of Representatives who have had access to the other Party's Evaluation Material, unless such use shall infringe on any of such Party's patent rights, trademark rights or copyright rights",
      "permission", "neither ... will be restricted from", "BothParties", "Party",
      [A("use", "using", "UseForOtherPurposes", "kind_of",
         obj=O("the information contained in the Evaluation Material that is retained in the minds of Representatives who have had access to the other Party's Evaluation Material", True))],
      details=[D("override", "Notwithstanding any other provision of this Agreement")],
      exc=[L("InfringesIPRights", "unless such use shall infringe on any of such Party's patent rights, trademark rights or copyright rights", verb="infringe", object="IP rights")])]}

# ------------------------------------------------------------------ ret_28
G["ret_28"] = {"statements": [
    S("The Receiving Party agrees to treat all information provided by the Providing Party in connection with the Business Under Discussion to the Receiving Partner and/or any of its partners, directors, officers, employees, affiliates, insurers, agents, advisors or auditors (the \"Representatives\"), regardless of the manner in which it is so furnished, together with any analyses, compilations, data, studies or other documents or records, whether of an oral, written or electronically retrievable nature (collectively the \"Information\"), as strictly confidential",
      "obligation", "agrees to", "ReceivingParty", "The Receiving Party",
      [A("treat", "treat", obj=O("all information provided by the Providing Party in connection with the Business Under Discussion to the Receiving Partner and/or any of its partners, directors, officers, employees, affiliates, insurers, agents, advisors or auditors", True),
         manner=("as strictly confidential", "StrictlyConfidential"))],
      details=[D("defined_term", "the \"Representatives\""), D("scope", "regardless of the manner in which it is so furnished"),
               D("also_covers", "together with any analyses, compilations, data, studies or other documents or records"),
               D("form", "whether of an oral, written or electronically retrievable nature"), D("defined_term2", "collectively the \"Information\"")]),
    S("together with any analyses, compilations, data, studies or other documents or records, whether of an oral, written or electronically retrievable nature (collectively the \"Information\")",
      "includes", "together with", "ConfidentialInfo", "Information",
      items=[I("any analyses, compilations, data, studies or other documents or records", "AnalysesDataRecords"),
             I("oral", "Oral", "oral_visual"), I("written", "Written"), I("electronically retrievable", "Electronic")],
      details=[D("form", "whether of an oral, written or electronically retrievable nature"), D("defined_term", "collectively the \"Information\"")]),
]}

# ------------------------------------------------------------------ ret_30
VEND = "VENDOR nor any of its employees, agents, contractors, or subcontractors"
OBJ30 = O("any of the Confidential Information or of any files, compilation, study, report, or analysis or data base containing, based on, or derived from the Confidential Information", True)
TP30 = ("to any other person or entity", "ThirdParty")
G["ret_30"] = {"statements": [
    S("Neither VENDOR nor any of its employees, agents, contractors, or subcontractors shall sell, release, transfer, reprint, duplicate, recreate, disclose or permit the disclosure to any other person or entity of any of the Confidential Information or of any files, compilation, study, report, or analysis or data base containing, based on, or derived from the Confidential Information without the express written consent of UNIVERSITY and in full compliance with applicable state and federal privacy laws",
      "prohibition", "Neither ... shall", "ReceivingParty", VEND,
      [A("sell", "sell", "ShareWithThirdParties", obj=OBJ30, recipient=TP30), A("release", "release", "ShareWithThirdParties", obj=OBJ30, recipient=TP30),
       A("transfer", "transfer", "ShareWithThirdParties", obj=OBJ30, recipient=TP30),
       A("reprint", "reprint", "CreateCopy", obj=OBJ30), A("duplicate", "duplicate", "CreateCopy", obj=OBJ30), A("recreate", "recreate", "CreateCopy", obj=OBJ30),
       A("disclose", "disclose", "ShareWithThirdParties", obj=OBJ30, recipient=TP30),
       A("permit_disclosure", "permit the disclosure", "ShareWithThirdParties", obj=OBJ30, recipient=TP30)],
      exc=[ALL("without the express written consent of UNIVERSITY and in full compliance with applicable state and federal privacy laws",
               L("UniversityExpressWrittenConsent", "the express written consent of UNIVERSITY", agent="UNIVERSITY", verb="consent"),
               L("FullComplianceWithPrivacyLaws", "in full compliance with applicable state and federal privacy laws", verb="comply"))])]}

# ------------------------------------------------------------------ ret_33
G["ret_33"] = {"statements": [
    S("\"Information\" means all oral, written, or other information whatsoever, including information in documents and other recording media and information embodied in any item, which in connection with the Matter, is",
      "includes", "means", "ConfidentialInfo", "Information",
      items=[I("oral", "Oral", "oral_visual"), I("written", "Written"),
             I("other information whatsoever", "OtherInformation", "technical", "non_technical", "oral_visual"),
             I("information in documents and other recording media", "InfoInDocuments"), I("information embodied in any item", "InfoEmbodied")],
      details=[D("scope", "which in connection with the Matter, is"), D("illustration", "including")], exh=True)]}

# ------------------------------------------------------------------ ret_36
G["ret_36"] = {"statements": [
    S("Confidential Information shall mean: i) all technical, financial and business information disclosed by one Party to the other Party or by another Haldex Group entity to the Supplier including, but not limited to, documents, data, information, prototypes or components relating to devices, methods, materials, apparatus, designs, research, yields and specifications",
      "includes", "shall mean", "ConfidentialInfo", "Confidential Information",
      items=[I("technical", "Technical", "technical"), I("financial", "Financial", "non_technical"), I("business information", "Business", "non_technical"),
             I("documents, data, information, prototypes or components relating to devices, methods, materials, apparatus, designs, research, yields and specifications", "ListedMaterials", "technical")],
      details=[D("disclosure", "disclosed by one Party to the other Party or by another Haldex Group entity to the Supplier"),
               D("illustration", "including, but not limited to")], exh=True)]}

# ------------------------------------------------------------------ ret_37
Q37 = "information that: (d) is or has been lawfully disclosed by a third Party to the Receiving Party without an obligation of confidentiality"
G["ret_37"] = {"statements": [
    S("The definition of Information shall not include " + Q37, "excludes", "shall not include", "ConfidentialInfo", "Information",
      items=[I(Q37, "LawfullyDisclosedByThirdParty")], details=[D("scope", "The definition of")]),
    S("The definition of Information shall not include " + Q37, "permission", "shall not include", "ReceivingParty", "the Receiving Party",
      [A("receive", "disclosed", "AcquireFromThirdParty", obj=O("information", True), source=("by a third Party", "ThirdParty"),
         recipient=("to the Receiving Party", "ReceivingParty"), manner=("lawfully", "Lawfully"))],
      details=[D("condition_of_receipt", "without an obligation of confidentiality"), D("scope", "The definition of"), D("tense", "is or has been")], inferred=True),
]}

# ------------------------------------------------------------------ ret_38
REPS38 = "except for disclosures to its directors, executive officers and representatives of its advisors (such as independent accountants, investment bankers, consultants and attorneys) acting on its behalf (collectively, its \"Representatives\") who in each case, in such party's reasonable judgment, need to know such information for the purpose of evaluating a possible Transaction and who are set forth on Annex A hereto, as it may be amended by the parties from time to time"
G["ret_38"] = {"statements": [
    S("Each of PictureTel and Polycom shall (ii) not disclose the Confidential Information to any third party, " + REPS38,
      "prohibition", "shall not", "ReceivingParty", "Each of PictureTel and Polycom",
      [A("disclose", "disclose", "ShareWithThirdParties", obj=O("the Confidential Information", True), recipient=("to any third party", "ThirdParty"))],
      exc=[ALL(REPS38,
               L("RecipientIsRepresentative", "directors, executive officers and representatives of its advisors (such as independent accountants, investment bankers, consultants and attorneys) acting on its behalf", object="Representatives"),
               L("NeedToKnowForTransaction", "in each case, in such party's reasonable judgment, need to know such information for the purpose of evaluating a possible Transaction", verb="need_to_know"),
               L("ListedInAnnexA", "who are set forth on Annex A hereto, as it may be amended by the parties from time to time", verb="list"))])]}

# ------------------------------------------------------------------ ret_41
RQ41 = "Immediately upon the written request by the Disclosing Party at any time"
OBJ41 = O("all Proprietary Information and all documents or media containing any such Proprietary Information and any and all copies or extracts thereof", True)
G["ret_41"] = {"statements": [
    S("Immediately upon the written request by the Disclosing Party at any time, the Receiving Party will return to the Disclosing Party all Proprietary Information and all documents or media containing any such Proprietary Information and any and all copies or extracts thereof",
      "obligation", "will", "ReceivingParty", "the Receiving Party",
      [A("return", "return", "ReturnOrDestroy", obj=OBJ41, recipient=("to the Disclosing Party", "DisclosingParty"), time=("Immediately", "Immediately"))],
      cond=[L("WrittenRequestByDiscloser", "upon the written request by the Disclosing Party at any time", agent="DisclosingParty", verb="request")]),
    S("return to the Disclosing Party all Proprietary Information and all documents or media containing any such Proprietary Information and any and all copies or extracts thereof",
      "prohibition", "return", "ReceivingParty", "the Receiving Party",
      [A("retain", "return", "RetainCopies", obj=OBJ41, recipient=("to the Disclosing Party", "DisclosingParty"))],
      cond=[L("WrittenRequestByDiscloser", "upon the written request by the Disclosing Party at any time", agent="DisclosingParty", verb="request")], inferred=True),
    S("save that where such Proprietary Information is a form incapable of return or has been copied or transcribed into another document, it shall be destroyed or erased, as appropriate",
      "obligation", "shall", "ReceivingParty", "",
      [A("destroy", "destroyed", "ReturnOrDestroy", obj=O("it", True), manner=("as appropriate", "AsAppropriate")),
       A("erase", "erased", "ReturnOrDestroy", obj=O("it", True), manner=("as appropriate", "AsAppropriate"))],
      cond=[L("FormIncapableOfReturnOrCopied", "save that where such Proprietary Information is a form incapable of return or has been copied or transcribed into another document",
              object="Proprietary Information")]),
]}

# ------------------------------------------------------------------ ret_45 (retrieval miss: independent development is not in this text)
G["ret_45"] = {"statements": [
    S("The Recipient's obligations under this Agreement do not apply to, and the term Confidential Information does not include, any information to the extent to which the Recipient can prove to the Disclosers' reasonable satisfaction has been agreed by the Disclosers in writing as being excluded from Confidential Information",
      "permission", "do not apply to", "ReceivingParty", "The Recipient's",
      [A("be_free_of_obligations", "obligations under this Agreement", obj=O("any information", True))],
      cond=[L("AgreedExcludedInWriting", "to the extent to which the Recipient can prove to the Disclosers' reasonable satisfaction has been agreed by the Disclosers in writing as being excluded from Confidential Information")],
      details=[D("also", "and the term Confidential Information does not include")], inferred=True),
    S("The Recipient shall not be in breach of its obligations under this Agreement to the extent that any Confidential Information received by it may be required by law or regulation having force of law; or the rules of any court or other body of competent jurisdiction; or any governmental body to be disclosed",
      "permission", "shall not be in breach of", "ReceivingParty", "The Recipient",
      [A("disclose", "disclosed", "DiscloseUnderLegalProcess", obj=O("any Confidential Information received by it", True))],
      details=[D("scope", "its obligations under this Agreement")],
      cond=[ANY("to the extent that any Confidential Information received by it may be required by law or regulation having force of law; or the rules of any court or other body of competent jurisdiction; or any governmental body to be disclosed",
                L("RequiredByLaw", "required by law or regulation having force of law", object="disclosure"),
                L("RequiredByCourtRules", "the rules of any court or other body of competent jurisdiction", object="disclosure"),
                L("RequiredByGovernmentBody", "any governmental body", object="disclosure"))]),
    S("provided in each case the Recipient, to the extent permitted by the foregoing requirement, immediately notifies the Disclosers in writing of any request or requirement for disclosure and of all relevant surrounding circumstances prior to disclosure",
      "obligation", "provided in each case", "ReceivingParty", "the Recipient",
      [A("notify", "notifies", "NotifyOnLegalDisclosure", obj=O("any request or requirement for disclosure and of all relevant surrounding circumstances", True),
         recipient=("the Disclosers", "DisclosingParty"), manner=("in writing", "InWriting"), time=("immediately ... prior to disclosure", "BeforeDisclosure"))],
      details=[D("limit", "to the extent permitted by the foregoing requirement")], inferred=True),
    S("and takes into account any representations made by the Disclosers in relation to the disclosure", "obligation", "takes into account", "ReceivingParty", "the Recipient",
      [A("consider", "takes into account", obj=O("any representations made by the Disclosers in relation to the disclosure"))]),
]}

# ------------------------------------------------------------------ ret_59
G["ret_59"] = {"statements": [
    S("Neither Investor nor any of its Representatives shall, directly or indirectly, (y) reproduce or otherwise copy any Evaluation Material except in connection with the Transaction",
      "prohibition", "Neither ... shall", "ReceivingParty", "Investor nor any of its Representatives",
      [A("reproduce", "reproduce", "CreateCopy", obj=O("any Evaluation Material", True), manner=("directly or indirectly", "DirectOrIndirect")),
       A("copy", "otherwise copy", "CreateCopy", obj=O("any Evaluation Material", True), manner=("directly or indirectly", "DirectOrIndirect"))],
      exc=[L("InConnectionWithTransaction", "except in connection with the Transaction", object="Evaluation Material")])]}

# ------------------------------------------------------------------ ret_5 (demo: the notify-on-legal-disclosure clause)
LEGAL5 = "is required to be disclosed by law, regulation or any competent governmental, judicial or regulatory authority, or by a recognized stock exchange, or in response to a request from a regulatory body with a supervisory role over Recipient or any of its Affiliates"
G["ret_5"] = {"statements": [
    S("The obligations in Clause 5.1 shall not apply for Confidential Information that: 5.2.4. " + LEGAL5,
      "permission", "shall not apply", "ReceivingParty", "Recipient",
      [A("disclose", "disclosed", "DiscloseUnderLegalProcess", obj=O("Confidential Information", True))],
      details=[D("scope", "The obligations in Clause 5.1")],
      cond=[ANY(LEGAL5,
                L("RequiredByLawOrRegulation", "is required to be disclosed by law, regulation", verb="require", object="disclosure"),
                L("RequiredByAuthority", "any competent governmental, judicial or regulatory authority", verb="require", object="disclosure"),
                L("RequiredByStockExchange", "by a recognized stock exchange", verb="require", object="disclosure"),
                L("RequestFromSupervisoryRegulator", "in response to a request from a regulatory body with a supervisory role over Recipient or any of its Affiliates", verb="request", object="disclosure"))]),
    S("in which case Recipient will (or, if Recipient's Representative is subject to the disclosure obligation, Recipient will procure that such Representative will), in each case to the extent permitted by law, regulation or the relevant authority: a) inform Discloser of the circumstances of the disclosure and the information that will be disclosed as soon as reasonably practicable",
      "obligation", "will", "ReceivingParty", "Recipient",
      [A("inform", "inform", "NotifyOnLegalDisclosure", obj=O("the circumstances of the disclosure and the information that will be disclosed"),
         recipient=("Discloser", "DisclosingParty"), time=("as soon as reasonably practicable", "AsSoonAsReasonablyPracticable"))],
      details=[D("alternative_actor", "or, if Recipient's Representative is subject to the disclosure obligation, Recipient will procure that such Representative will"),
               D("limit", "in each case to the extent permitted by law, regulation or the relevant authority")],
      cond=[L("RequiredToDiscloseUnderLegalProcess", "in which case", verb="require", object="disclosure")]),
]}

if __name__ == "__main__":
    json.dump(G, open("a3_gold.json", "w"), indent=1)
    print("wrote a3_gold.json with", len(G), "rows")

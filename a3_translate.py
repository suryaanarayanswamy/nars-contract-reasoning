"""
A3 translator: asks an LLM to translate a clause into the open A3 frames (see a3_core.py), repairs flagged
statements, and runs an independent faithfulness check. The translator NEVER sees the hypothesis.

Needs OPENAI_API_KEY (type it only in your own terminal).  Results are cached in a3_cache.json.
"""
import hashlib, json, os
import a3_core as K

PROMPT_VERSION = "a4.1"
CACHE_FILE = os.environ.get("A3_CACHE", "a3_cache.json")

SYSTEM = """You are a legal-logic translator. You receive a passage of a contract (or a single claim about a contract) and must translate
ALL of its meaning into structured statements. NOTHING may be dropped, summarised or merged. A program will check that every content word of
the passage is represented in some field of your output, and will list every word you missed. You are not told what the translation will be
used for; translate what the text says, completely and faithfully.

Output ONLY a JSON object:
{"statements": [ STATEMENT, ... ],
 "ignored":    [ {"text": "<verbatim words>", "why": "heading | list marker | connective | truncated fragment"} ]}

STATEMENT = {
 "quote": "<verbatim words of the passage this statement comes from, copied CONTIGUOUSLY (may skip list markers like (a)); never rejoin separated pieces into a new sentence - if the passage is interrupted, use '...' between the pieces or make two statements>",
 "force": "obligation | prohibition | permission | includes | excludes | survival | fact",
 "force_text": "<the modal words, verbatim: 'shall not', 'may', 'will not be restricted from', 'means'>",
 "agent": {"role": "<PascalCase role, see rule 6>", "name": "<how the passage names them, verbatim, or '' if unstated>"},
 "acts": [ {"verb": "<lemma>", "verb_text": "<verbatim>", "object": {"text": "<verbatim>"},
            "slots": {"recipient": {"text": "...", "term": "PascalCase"}, "purpose": {...}, "manner": {...}, "time": {...}, "place": {...}, "source": {...}} } ],
 "items": [ {"text": "<verbatim>", "term": "PascalCase"} ],
 "exhaustive": false,
 "details": [ {"slot": "scope | origin | definition | connective | ...", "text": "<verbatim>"} ],
 "conditions": [ COND ],   "exceptions": [ COND ],
 "inferred": false }
COND = {"atom": "PascalCase", "text": "<verbatim>", "frame": {"agent": "...", "verb": "...", "object": "..."}}
     | {"text": "<verbatim>", "any": [COND, ...]}  |  {"text": "<verbatim>", "all": [COND, ...]}

HOW TO TRANSLATE
1. Cover everything. Every verb, object, recipient, purpose, manner, time, condition and exception goes into a field, and every field's text is
   copied VERBATIM (it is matched against the passage). If something fits no field, put it in "details". Words like "Additionally",
   "regardless of ...", "whether or not ...", "(collectively the "Information")", "as defined herein" go in "details" or the relevant slot.
2. One act per verb. "shall sell, release, transfer, reprint, duplicate, recreate or disclose" = SEVEN acts, one per verb, sharing the same
   object and recipient. Alternatives joined by "or"/"and" each get their own act (or their own item). (A single short claim may keep
   "destroy or return" as one verb phrase.)
3. force:
   obligation = must/shall/agrees to/will/undertakes.  prohibition = shall not/will not/agrees not to/no right is granted/only ... (restrictive).
   permission = may/entitled/free to, AND every exemption wording: "obligations do not apply to X", "shall not be in breach if X",
                "neither Party will be restricted from X", "shall not include information that ..." => the exempted thing is PERMITTED.
   includes / excludes = what a defined term covers / does not cover ("means", "includes", "shall not include", "shall only include").
                Set "exhaustive": true when the list is complete ("means", "only").
   survival = obligations survive termination/expiry.  fact = any other statement of fact or acknowledgement (ownership, definitions of parties).
4. "without X-ing ..." states a PROHIBITION of its own: "return all materials without retaining any copies" = obligation (return) +
   prohibition (retain copies). Emit both statements.
5. Conditions vs exceptions. condition = statement holds ONLY IF it is true ("provided that", "upon request", "if", "who need to know").
   exception = statement does NOT hold when it is true ("except", "unless", "without the consent of", "other than", "save that" on a prohibition).
   Several alternatives = ONE "any" condition with one leaf each. Requirements that must ALL hold = "all".
6. agent.role: use ReceivingParty for the party receiving/using the information (the Recipient, "you", the Vendor, the Investor, the licensee...),
   DisclosingParty for the party disclosing/owning it, BothParties for "each Party"/"neither Party"/"the Parties", Agreement for the contract itself,
   ConfidentialInfo for a defined term for the information itself ("Information", "Proprietary Information"), Obligations for survival statements.
   For other kinds of contract use the defined role in PascalCase (Licensor, Tenant...). Put the contract's own name in agent.name.
   A passive sentence ("The List shall not be copied") is about whoever is bound: usually ReceivingParty.
7. object / slots: object = what the verb acts on; recipient = to/with whom; purpose = for what; manner = how; time = when; place = where;
   source = from whom/where. "term" is a short PascalCase label of the slot text.
8. items (for includes/excludes): one item per kind of information listed ("technical", "financial", "business information", "oral information").
9. "inferred": true ONLY when a statement is implied rather than stated. Add it as an extra statement, keep its quote and force_text verbatim from the
   passage, and mark it inferred. Typical cases: information that the definition EXCLUDES because it is public, already known, independently developed or
   received from a third party => the recipient MAY use/receive/disclose it freely; "return all copies" => the recipient may not retain copies.
   Do not infer anything else EXCEPT these two general patterns, which you must always add:
   (a) An exclusion or "shall not apply" defined by something the recipient DOES or GETS (develops, creates, receives, obtains, acquires, already
       knew, can document) => besides the statement itself, add an inferred PERMISSION whose verb is that activity itself (develop / receive / acquire / know),
       with the source, manner or object as slots. Example: "does not include information independently developed by the Receiver" =>
       inferred permission: Receiver MAY develop (manner: independently) information.
   (b) A duty that presupposes access ("restrict access to ... to those who need it", "require employees and advisors to sign ...",
       "shall ensure its Representatives keep ...") => inferred permission: the recipient MAY disclose / share the information with those people.
10. A DEFINITION or SCOPE of the protected information ("X means all information ...", "(collectively, the 'Information')", "whether oral, written or
   electronic", "includes, without limitation ...") is ALWAYS a statement with force "includes" (set "exhaustive": true when it says "means" / "shall be"
   and not "including"), with one item per listed kind or form of information. Never turn a definition into an act such as "refer" or "define".
   force must be exactly one of: obligation, prohibition, permission, includes, excludes, survival, fact.

EXAMPLES (invented text, only to show the format)
Passage: "The Licensee shall, upon termination, promptly return or destroy all Materials without keeping any duplicates, save as required by law."
{"statements": [
 {"quote": "The Licensee shall, upon termination, promptly return or destroy all Materials", "force": "obligation", "force_text": "shall",
  "agent": {"role": "ReceivingParty", "name": "The Licensee"},
  "acts": [ {"verb": "return", "verb_text": "return", "object": {"text": "all Materials"}, "slots": {"time": {"text": "promptly", "term": "Promptly"}}},
            {"verb": "destroy", "verb_text": "destroy", "object": {"text": "all Materials"}, "slots": {"time": {"text": "promptly", "term": "Promptly"}}} ],
  "conditions": [ {"atom": "Termination", "text": "upon termination", "frame": {"verb": "terminate", "object": "Agreement"}} ], "exceptions": []},
 {"quote": "without keeping any duplicates, save as required by law", "force": "prohibition", "force_text": "without keeping",
  "agent": {"role": "ReceivingParty", "name": "The Licensee"},
  "acts": [ {"verb": "keep", "verb_text": "keeping", "object": {"text": "any duplicates"}, "slots": {}} ],
  "conditions": [ {"atom": "Termination", "text": "upon termination", "frame": {"verb": "terminate", "object": "Agreement"}} ],
  "exceptions": [ {"atom": "RequiredByLaw", "text": "save as required by law", "frame": {"verb": "require", "object": "retention"}} ]} ],
 "ignored": []}

Passage: "Nothing herein shall prevent the Recipient from using general skills and know-how it retains in its memory, unless the use identifies the Discloser."
{"statements": [
 {"quote": "Nothing herein shall prevent the Recipient from using general skills and know-how it retains in its memory, unless the use identifies the Discloser",
  "force": "permission", "force_text": "Nothing herein shall prevent ... from", "agent": {"role": "ReceivingParty", "name": "the Recipient"},
  "acts": [ {"verb": "use", "verb_text": "using", "object": {"text": "general skills and know-how it retains in its memory"}, "slots": {}} ],
  "conditions": [], "exceptions": [ {"atom": "UseIdentifiesDiscloser", "text": "unless the use identifies the Discloser", "frame": {"verb": "identify", "object": "Discloser"}} ]} ],
 "ignored": []}
"""

ALIGN_SYSTEM = """You compare numbered statements translated from a contract with ONE claim (the hypothesis). For each statement say how the
ACT or ITEM it describes relates to the hypothesis. Ignore whether the statement allows, forbids or requires it: that is handled elsewhere.
Relations:
  same      = the statement describes the same act as the hypothesis (same meaning of verb; object, recipient and source compatible)
  kind_of   = the statement's act is one specific way of doing the hypothesis act ('reproduce' for 'create a copy'; 'return' for 'destroy or return';
              'share with consultants' for 'share with third parties')
  broader   = the statement's act covers the hypothesis act and more ('dispose of' for 'destroy'; 'disclose to anyone' for 'disclose to consultants')
  outside   = ONLY for items: the item is information of a kind the hypothesis category does NOT cover (hypothesis 'only technical information',
              item 'business information' or 'any information whatsoever')
  conflicts = the statement is an OBLIGATION (or a ban) whose fulfilment is incompatible with the hypothesis act, although the verbs differ:
              'must return or destroy all copies' conflicts with 'may retain copies after the return or destruction'; 'must delete' conflicts with 'may keep'.
              Use it only for real incompatibility, never for a merely different topic.
  unrelated = anything else: different verb meaning; a different kind of recipient (own employees vs third parties; a court or regulator vs third parties);
              the object is not what the hypothesis is about.
For statements of kind 'item' (what a definition includes) 'same', 'kind_of' and 'broader' mean the item covers the hypothesis' kind of information.
The same holds for an item a definition EXCLUDES ('does not include X'): 'same', 'kind_of' or 'broader' mean the hypothesis is about doing something
with exactly that kind of information (hypothesis 'develop similar information independently', excluded item 'information independently developed by the receiving Party').
Judge the ACT (verb) separately from the object: if the contract names a document or data set that, in context, is the protected
information (a 'List', 'Evaluation Material', 'the publications', 'Proprietary Information'), treat the object as compatible with 'Confidential Information'.
Several verbs listed together ('copy, reprint or disseminate') are separate acts: align each on its own meaning.
For a claim of the form 'only includes X': an item of a clearly different category from X (products, customer data, financial or business information) is
'outside', not 'unrelated'.
Be strict about the verb meaning: when unsure about the ACT answer 'unrelated'. Give a one-sentence reason quoting the decisive words.
Output ONLY JSON: {"alignments": [ {"i": <int>, "relation": "same|kind_of|broader|outside|conflicts|unrelated", "why": "..."} ]}"""

REPAIR_SYSTEM = """You are REPAIRING an earlier translation of a legal passage. An automatic checker found the problems listed below.
Return the COMPLETE corrected JSON ({"statements": [...], "ignored": [...]}) in the same format as before, fixing what the problems point at:
  unrepresented_words  -> these content words of the passage are in no field: add them to the right slot/detail/condition, or add the
                          missing statement (a missing verb = a missing act; a missing clause = a missing statement)
  ungrounded_quote / ungrounded_slot / ungrounded_ignored -> the text was not copied verbatim from the passage: copy it exactly
  modality_mismatch / exemption_read_as_prohibition -> re-read the wording: "not be restricted / not in breach / do not apply" are PERMISSIONS
  exception_as_condition / condition_as_exception -> "except/unless/without/save" on a prohibition = exception; "if/provided/upon" = condition
  without_clause_missing_prohibition -> add the prohibition that "without X-ing" states
  verb_mapping_disagrees / verb_maybe_hypothesis_verb / object_not_ci -> reconsider maps_to / is_ci using the rules
  compressed_condition -> use an "any" condition with one leaf per alternative
  verifier_* -> the independent reviewer says meaning was missing, added or reversed: fix exactly that
Keep every correct statement unchanged. If a flag is a false alarm, leave that statement alone. Do not add commentary."""

VERIFY_SYSTEM = """You are a strict reviewer of legal translations. You get (1) a passage of a contract and (2) a plain-English
rendering of a structured translation of it. Compare them sentence by sentence and report ONLY real problems:
  "missing"  : meaning in the passage that the rendering does not express (an obligation, verb, party, condition, exception, purpose, qualifier)
  "added"    : meaning in the rendering that the passage does not say
  "reversed" : something the rendering turns into its opposite (a permission shown as a prohibition, an exception as a condition, etc.)
Output ONLY JSON: {"problems": [ {"kind": "missing|added|reversed", "passage_words": "<verbatim>", "explain": "<one sentence>"} ]}
Return {"problems": []} if the rendering is faithful. Do not nitpick wording; flag only differences of meaning."""


class LLMTranslator:
    def __init__(self, model="gpt-4o", verify_model=None, persona=""):
        self.persona = persona                       # an extra reading instruction: gives each agent a different point of view
        self.sys = SYSTEM + ("\n\nYOUR POINT OF VIEW: " + persona if persona else "")
        self.asys = ALIGN_SYSTEM + ("\n\nYOUR POINT OF VIEW: " + persona if persona else "")
        self.model = model
        self.verify_model = verify_model or model
        self._client = None
        self.cache = json.load(open(CACHE_FILE)) if os.path.exists(CACHE_FILE) else {}

    PROVIDERS = {   # "provider:model" -> OpenAI-compatible endpoint. Free options: ollama (local), groq / gemini (free tiers, rate limited)
        "openai": (None, "OPENAI_API_KEY"),
        "ollama": ("http://localhost:11434/v1", None),
        "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
        "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY"),
    }

    def _client_for(self, model):
        prov, _, name = model.partition(":") if model.split(":")[0] in self.PROVIDERS else ("openai", "", model)
        if not hasattr(self, "_clients"):
            self._clients = {}
        if prov not in self._clients:
            from openai import OpenAI
            base, keyvar = self.PROVIDERS[prov]
            key = os.environ.get(keyvar) if keyvar else "ollama"
            if keyvar and not key:
                raise SystemExit(f"Set {keyvar} in your terminal first (export {keyvar}=...) for provider '{prov}'.")
            self._clients[prov] = OpenAI(base_url=base, api_key=key) if base else OpenAI()
        return self._clients[prov], (name or model)

    def _chat(self, model, system, user):
        client, model = self._client_for(model)
        r = client.chat.completions.create(
            model=model, temperature=0, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return r.choices[0].message.content

    def _json(self, model, system, user):
        k = hashlib.sha1(f"{PROMPT_VERSION}|{model}|{system}|{user}".encode()).hexdigest()
        if k in self.cache:
            return self.cache[k]
        out = {"statements": [], "ignored": [], "_parse_error": True}
        for attempt in range(2):
            try:
                out = json.loads(self._chat(model, system, user if attempt == 0 else user + "\n\nReturn valid JSON only."))
                break
            except json.JSONDecodeError:
                continue
        self.cache[k] = out
        json.dump(self.cache, open(CACHE_FILE, "w"))
        return out

    def evidence(self, ex):
        out = self._json(self.model, self.sys, "Passage:\n" + ex["evidence"].strip() + "\n\nOutput:")
        return {"statements": out.get("statements", []), "ignored": out.get("ignored", [])}

    def repair(self, evidence, stmts, flags, ignored):
        real = [f for f in flags if f.get("level") != "info"]
        if not real:
            return None
        user = ("Passage:\n" + evidence.strip() + "\n\nCurrent translation:\n" +
                json.dumps({"statements": stmts, "ignored": ignored}, indent=1) +
                "\n\nProblems found:\n" + "\n".join(f"- {f['type']}: {f['detail']}" for f in real) + "\nOutput:")
        out = self._json(self.model, REPAIR_SYSTEM, user)
        return out if out.get("statements") else None

    def implied(self, evidence, stmts):
        """Second look: statements the passage clearly IMPLIES but the first translation did not carry (marked inferred)."""
        user = ("Passage:\n" + evidence.strip() + "\n\nAlready translated:\n" + json.dumps({"statements": stmts}, indent=1) +
                "\n\nAdd ONLY the missing inferred statements (rule 9 and rule 10), each with \"inferred\": true, quote and force_text copied verbatim "
                "from the passage. If nothing is missing return {\"statements\": [], \"ignored\": []}. Output:")
        out = self._json(self.model, self.sys, user)
        sts = out.get("statements") if isinstance(out, dict) else None
        return [x for x in (sts or []) if isinstance(x, dict)]

    def verify(self, evidence, rendered):
        user = "Passage:\n" + evidence.strip() + "\n\nRendering of the translation:\n" + "\n".join(f"- {r}" for r in rendered)
        out = self._json(self.verify_model, VERIFY_SYSTEM, user)
        return [{"type": "verifier_" + str(p.get("kind", "problem")),
                 "detail": f"{p.get('passage_words', '')[:90]} -- {p.get('explain', '')[:140]}"} for p in out.get("problems", [])]

    def hypothesis_frame(self, text):
        """The hypothesis is translated by the SAME prompt as the contract."""
        out = self._json(self.model, self.sys, "Passage:\n" + text.strip() + "\n\nOutput:")
        sts = out.get("statements") or []
        return sts[0] if sts and isinstance(sts[0], dict) else None

    def align(self, ex, hyp_stmt, hyp, units, stmts):
        payload = {"hypothesis": hyp["desc"],
                   "statements": [{"i": i, "kind": u["kind"], "text": u["desc"], "from_quote": stmts[u["stmt"]]["quote"][:200]}
                                  for i, u in enumerate(units)]}
        out = self._json(self.model, self.asys, json.dumps(payload, indent=1))
        got = {}
        for a in out.get("alignments", []) or []:
            if isinstance(a, dict) and isinstance(a.get("i"), int):
                rel = a.get("relation") if a.get("relation") in K.RELATIONS else "unrelated"
                got[a["i"]] = (rel, str(a.get("why", ""))[:200])
        return [got.get(i, ("unrelated", "no answer from the aligner")) for i in range(len(units))]

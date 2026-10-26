"""
A3 core: lossless-by-construction translation checks + deterministic Narsese compiler. NO AI calls here.

Why A3 exists
-------------
A2 forced every clause into 6 predicates x 15 canonical actions. Anything that did not fit (a second verb in
a list, a purpose, a recipient, "without retaining copies", the actor's name) was silently dropped, which is the
"partial translation" problem. A3 keeps EVERYTHING in an open structure and then checks, mechanically, that every
content word of the contract text is accounted for in some slot.

A translated statement (JSON):
{
 "id": "s1",
 "quote":      "<verbatim words of the contract this statement comes from>",
 "force":      "obligation | prohibition | permission | includes | excludes | survival",
 "force_text": "<the modal words, verbatim: 'shall not', 'may', 'will not be restricted from'>",
 "agent":      {"role": "ReceivingParty|DisclosingParty|BothParties|Agreement|ConfidentialInfo|Obligations|ThirdParty|Other",
                "name": "<how the contract names them, verbatim>"},
 "acts": [ {                                    # one entry per verb / alternative  (not for includes/excludes/survival)
     "verb": "copy",                            # free lemma of the verb actually used
     "verb_text": "reproduce",                  # verbatim
     "maps_to": "CreateCopy" | null,            # which of the 15 hypothesis actions this is (see a2_vocab.ACTIONS)
     "relation": "same | kind_of | broader",    # how the verb relates to maps_to
     "object": {"text": "...", "is_ci": true},  # is_ci: the object is the Confidential Information of this agreement
     "slots": {"recipient": {"text": "...", "term": "ThirdParty"}, "purpose": {...}, "manner": {...},
               "time": {...}, "place": {...}}   # any slot optional; each has verbatim text + a short PascalCase term
 } ],
 "items":      [ {"text": "...", "term": "...", "classes": ["technical","non_technical","oral_visual"]} ],  # includes/excludes
 "exhaustive": false,                           # includes: the definition lists ALL that is included ("means")
 "conditions": [ COND ],   # statement holds ONLY IF all of these
 "exceptions": [ COND ]    # statement does NOT hold if any of these
}
COND = {"atom": "PascalCase", "text": "<verbatim>", "frame": {"agent": "...", "verb": "...", "object": "..."}}   # leaf
     | {"text": "<verbatim>", "any": [COND, ...]}   | {"text": "<verbatim>", "all": [COND, ...]}

Also returned by the translator:  "ignored": [{"text": "<verbatim>", "why": "heading | list connective | ..."}]
"""
import re, copy, itertools
import a2_compile as C

ROLES = ("ReceivingParty", "DisclosingParty", "BothParties", "Agreement", "ConfidentialInfo",
         "Obligations", "ThirdParty", "Other")
FORCES = ("obligation", "prohibition", "permission", "includes", "excludes", "survival", "fact")
FORCE_PRED = {"obligation": "Obligated", "prohibition": "Prohibited", "permission": "Permitted",
              "includes": "Includes", "excludes": "Excludes", "survival": "Survives", "fact": "Fact"}
CLASS_ITEM = {"technical": "TechnicalInfo", "non_technical": "NonTechnicalInfo", "oral_visual": "VerbalInfo"}
# how a contract statement relates to a hypothesis (decided in the separate, logged alignment step - never by the translator)
RELATIONS = ("same", "kind_of", "broader", "outside", "conflicts", "unrelated")
SLOTS = ("recipient", "purpose", "manner", "time", "place", "source")
IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


# =============================================================================== tokens / locating
TOK = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?")
FUNCTION_WORDS = set("""the a an of to in on at by for with from as that which who whom whose any all each such this these
those is are was were be been being it its their his her or and but if unless except provided upon so than then there
herein hereof hereby hereunder thereof thereto therein whether also either both other another same
""".split())
UNITS = set("day days week weeks month months year years hour hours business percent".split())


def tokens(text):
    """[(word, start, end)] with list markers like (a) (ii) (y) dropped."""
    out = []
    for m in TOK.finditer(text):
        s, e = m.span()
        w = m.group(0).lower().replace("’", "'")
        pre, post = text[s - 1:s] if s else "", text[e:e + 1]
        if pre == "(" and post == ")" and re.fullmatch(r"[a-z]|[ivx]+|\d+", w):
            continue
        if post == ")" and pre in ("", " ") and re.fullmatch(r"[a-z]|[ivx]+|\d+", w):
            continue                                                  # "i)" style marker
        out.append((w, s, e))
    return out


def _find(seq, needle, start=0, end=None):
    end = len(seq) if end is None else end
    n = len(needle)
    for i in range(start, end - n + 1):
        if seq[i:i + n] == needle:
            return i
    return -1


def locate_all(text, ev_words, lo, hi):
    """Every occurrence (as token ranges) of each '...'-piece of `text` inside ev_words[lo:hi]."""
    out = []
    for p in re.split(r"\.\.\.|\u2026", text or ""):
        nt = [w for w, _, _ in tokens(p)]
        if not nt:
            continue
        pos = lo
        while True:
            i = _find(ev_words, nt, pos, hi)
            if i < 0:
                break
            out.append((i, i + len(nt)))
            pos = i + len(nt)
    return out


def _stitched(nt, ev_words, lo, hi):
    """Fallback: the quote was assembled from several places of the passage. Accept it only if EVERY word occurs in the passage,
    in order (runs of consecutive words are matched greedily); returns the token ranges used, else None."""
    hi = len(ev_words) if hi is None else hi
    ranges, pos, q = [], lo, 0
    while q < len(nt):
        best = None
        for i in range(pos, hi):
            if ev_words[i] != nt[q]:
                continue
            k = 0
            while q + k < len(nt) and i + k < hi and ev_words[i + k] == nt[q + k]:
                k += 1
            if best is None or k > best[1]:
                best = (i, k)
            if k >= 3 or (q + k == len(nt)):
                break
        if best is None:
            return None
        ranges.append((best[0], best[0] + best[1]))
        pos, q = best[0] + best[1], q + best[1]
    return ranges or None


def locate_tokens(text, ev_words, lo=0, hi=None):
    r = _locate_tokens(text, ev_words, lo, hi)
    if r is None:
        nt = [w for w, _, _ in tokens(re.sub(r"\.\.\.|\u2026", " ", text or ""))]
        if len(nt) >= 2:
            r = _stitched(nt, ev_words, lo, hi)
    return r


def _locate_tokens(text, ev_words, lo=0, hi=None):
    """Token ranges [(i, j)] where `text` (pieces separated by '...') occurs in order in ev_words[lo:hi]."""
    pieces = [p for p in re.split(r"\.\.\.|…", text or "") if tokens(p)]
    ranges, pos = [], lo
    for p in pieces:
        nt = [w for w, _, _ in tokens(p)]
        i = _find(ev_words, nt, pos, hi)
        if i < 0:
            return None
        ranges.append((i, i + len(nt)))
        pos = i + len(nt)
    return ranges or None


# =============================================================================== validation
def _ident(s):
    return isinstance(s, str) and IDENT.match(s)


def _clean_cond(c, errs, where):
    if not isinstance(c, dict):
        errs.append(f"{where}: condition is not an object"); return None
    out = {"text": str(c.get("text", ""))}
    for k in ("any", "all"):
        if k in c:
            kids = [_clean_cond(x, errs, where) for x in (c.get(k) or [])]
            kids = [x for x in kids if x]
            if not kids:
                errs.append(f"{where}: empty '{k}' condition"); return None
            out[k] = kids
            return out
    if not _ident(c.get("atom")) and c.get("text"):
        c = dict(c, atom=_term(None, c["text"], 5))            # harmless: name it from its own words
    if not _ident(c.get("atom")):
        errs.append(f"{where}: leaf condition needs a PascalCase 'atom', got {c.get('atom')!r}"); return None
    out["atom"] = c["atom"].replace("_", "")
    fr = c.get("frame")
    if isinstance(fr, dict):
        out["frame"] = {k: str(fr.get(k, "")) for k in ("agent", "verb", "object") if fr.get(k)}
    return out


def _as_text_obj(v, **extra):
    """LLMs sometimes give a bare string where an object is expected; accept it instead of crashing."""
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        return {"text": v, **extra}
    return {}


EXCL_WORDS = re.compile(r"\b(other\s+than|except(?:\s+for|\s+as)?|apart\s+from|besides|excluding|but\s+not|save\s+for)\b", re.I)
RESTRICTIVE = re.compile(r"^\s*(only|solely|exclusively)\b|\b(only|solely|exclusively)\s+(for|to|by|in|with|upon)\b", re.I)


def _keep_polarity(a):
    """A slot term is a short label made by the AI; it must not lose 'other than' (the claim 'no use for any purpose OTHER THAN X' is about the
    complement of X). Prefix OtherThan when the slot text says so and the term does not."""
    restrictive = False
    for key, sl in list(a["slots"].items()) + [("object", a["object"])]:
        t = sl.get("text", "") or ""
        if not t:
            continue
        if EXCL_WORDS.search(t):
            term = sl.get("term") or _term(None, t, 6)
            if not re.match(r"(OtherThan|Not|Except|Excl)", term):
                sl["term"] = "OtherThan" + term
        elif key != "object" and RESTRICTIVE.search(t):
            restrictive = True
            term = sl.get("term") or _term(None, t, 6)
            if not re.match(r"(OtherThan|Not)", term):
                sl["term"] = "OtherThan" + term
    return restrictive


def coerce_statement(s):
    """Repair harmless shape deviations (string instead of object, single item instead of list)."""
    if not isinstance(s, dict):
        return s
    s = dict(s)
    f = str(s.get("force") or "").strip().lower()
    if f and f not in FORCES:                                     # harmless synonyms for the force word
        syn = {"means": "includes", "mean": "includes", "define": "includes", "defines": "includes", "definition": "includes",
               "include": "includes", "contains": "includes", "covers": "includes", "exclude": "excludes", "excluded": "excludes",
               "state": "fact", "states": "fact", "statement": "fact", "declaration": "fact", "survive": "survival", "survives": "survival",
               "must": "obligation", "shall": "obligation", "obligated": "obligation", "required": "obligation", "duty": "obligation",
               "prohibited": "prohibition", "forbidden": "prohibition", "may": "permission", "permitted": "permission", "allowed": "permission"}
        if f in syn:
            if syn[f] == "includes" and f in ("means", "mean", "define", "defines", "definition"):
                s["exhaustive"] = True
            s["force"] = syn[f]
        elif s.get("items"):                                       # unknown word, but it lists items => a definition
            s["force"] = "includes"
        elif s.get("acts"):
            s["force"] = "fact"                                    # keep the content rather than drop it; the audit still checks it
    if isinstance(s.get("agent"), dict) and not s["agent"].get("role") and s["agent"].get("name"):
        s["agent"] = dict(s["agent"], role=_term(None, s["agent"]["name"], 3))      # name it from its own words
    if isinstance(s.get("agent"), str):
        s["agent"] = {"role": s["agent"] if s["agent"] in ROLES else "Other", "name": s["agent"]}
    acts = s.get("acts")
    if isinstance(acts, dict):
        acts = [acts]
    fixed = []
    for a in acts or []:
        if isinstance(a, str):
            a = {"verb": a, "verb_text": a}
        if isinstance(a, dict):
            a = dict(a)
            if isinstance(a.get("verb"), dict):
                a["verb"] = a["verb"].get("term") or a["verb"].get("text") or ""
            a["object"] = _as_text_obj(a.get("object"), is_ci=False)
            slots = a.get("slots")
            a["slots"] = {k: _as_text_obj(v) for k, v in slots.items()} if isinstance(slots, dict) else {}
            fixed.append(a)
    s["acts"] = fixed
    restr = [_keep_polarity(a) for a in fixed]
    if any(restr) and s.get("force") in ("obligation", "permission"):
        s["force"] = "prohibition"        # "must use ONLY for X" / "may use only for X" forbids every other use
        s["_restrictive"] = True
    items = s.get("items")
    if isinstance(items, (str, dict)):
        items = [items]
    s["items"] = [({"text": i, "classes": []} if isinstance(i, str) else i) for i in (items or []) if isinstance(i, (str, dict))]
    for k in ("conditions", "exceptions", "details"):
        v = s.get(k)
        if isinstance(v, (str, dict)):
            v = [v]
        out = []
        for c in v or []:
            if isinstance(c, str):
                c = {"slot": "detail", "text": c} if k == "details" else {"atom": _term(None, c), "text": c}
            if isinstance(c, dict) and k in ("conditions", "exceptions") and not (c.get("atom") or c.get("any") or c.get("all")):
                # the AI wrote a bare act-frame (role/verb/object/slots) instead of {atom,text,frame}: keep it as a condition
                if not c.get("text"):
                    bits = [str(c.get("verb_text") or c.get("verb") or "")]
                    o = c.get("object")
                    bits.append(str(o.get("text") if isinstance(o, dict) else o or ""))
                    for sl in (c.get("slots") or {}).values():
                        bits.append(str(sl.get("text") if isinstance(sl, dict) else sl or ""))
                    c = dict(c, text=str(s.get("quote") or " ".join(b for b in bits if b)), atom=_term(None, " ".join(bits), 5))
                else:
                    c = dict(c, atom=_term(None, c["text"], 5))
            if isinstance(c, dict):
                out.append(c)
        s[k] = out
    return s


def validate_statement(s):
    try:
        return _validate_statement(coerce_statement(s))
    except Exception as e:                      # never let one malformed statement crash a run
        return None, [f"malformed statement ({type(e).__name__}: {e})"]


def _validate_statement(s):
    errs = []
    if not isinstance(s, dict):
        return None, ["statement is not an object"]
    force = s.get("force")
    if force not in FORCES:
        errs.append(f"force must be one of {FORCES}, got {force!r}")
    ag = s.get("agent") or {}
    role = ag.get("role")
    if not _ident(role):
        errs.append(f"agent.role must be a PascalCase identifier (e.g. ReceivingParty), got {role!r}")
    else:
        role = role.replace("_", "")
    if not str(s.get("quote", "")).strip():
        errs.append("quote is empty")
    out = {"id": str(s.get("id", "")), "quote": str(s.get("quote", "")), "force": force,
           "force_text": str(s.get("force_text", "")), "agent": {"role": role, "name": str(ag.get("name", ""))},
           "acts": [], "items": [], "exhaustive": bool(s.get("exhaustive", False)), "inferred": bool(s.get("inferred", False)),
           "conditions": [], "exceptions": [], "segment": s.get("segment")}
    if force in ("obligation", "prohibition", "permission", "fact"):
        acts = s.get("acts") or []
        if not acts and force != "fact":
            errs.append("an obligation/prohibition/permission/fact needs at least one act")
        for a in acts:
            if not isinstance(a, dict) or not str(a.get("verb", "")).strip():
                errs.append("each act needs a 'verb'"); continue
            mt = a.get("maps_to")                      # optional hand label, used only by the test-oracle aligner
            if mt in ("", "none", "None"):
                mt = None
            rel = a.get("relation") or "same"
            obj = a.get("object") or {}
            slots = {}
            for k, v in (a.get("slots") or {}).items():
                if k in SLOTS and isinstance(v, dict) and str(v.get("text", "")).strip():
                    slots[k] = {"text": str(v["text"]), "term": _term(v.get("term"), v["text"])}
            out["acts"].append({"verb": re.sub(r"[^a-z0-9]+", "_", str(a["verb"]).lower()).strip("_"),
                                "verb_text": str(a.get("verb_text", "")), "maps_to": mt, "relation": rel,
                                "object": {"text": str(obj.get("text", "")), "is_ci": bool(obj.get("is_ci", False))},
                                "slots": slots})
    elif force in ("includes", "excludes"):
        for it in s.get("items") or []:
            cl = [c for c in (it.get("classes") or []) if c in CLASS_ITEM]       # optional hand label (oracle aligner only)
            if not str(it.get("text", "")).strip():
                errs.append("item needs text"); continue
            out["items"].append({"text": str(it["text"]), "term": _term(it.get("term"), it["text"]), "classes": cl})
        if not out["items"]:
            errs.append("includes/excludes needs at least one item")
    out["details"] = []
    for d in s.get("details") or []:
        if isinstance(d, dict) and str(d.get("text", "")).strip():
            out["details"].append({"slot": re.sub(r"[^a-z0-9]+", "_", str(d.get("slot", "detail")).lower()).strip("_") or "detail",
                                   "text": str(d["text"]), "term": _term(d.get("term"), d["text"])})
    for key in ("conditions", "exceptions"):
        for c in s.get(key) or []:
            cc = _clean_cond(c, errs, key)
            if cc:
                out[key].append(cc)
    return (None, errs) if errs else (out, [])


def _term(term, text, n=4):
    if isinstance(term, str) and _ident(term):
        return term.replace("_", "")
    ws = [w for w, _, _ in tokens(text) if w not in FUNCTION_WORDS][:n]
    return "".join(w.capitalize() for w in ws) or "Unspecified"


# =============================================================================== ledger (nothing may be silently lost)
def _walk_cond_texts(c, acc):
    acc.append(c["text"])
    for k in ("any", "all"):
        for kid in c.get(k, []):
            _walk_cond_texts(kid, acc)


def _slot_texts(s):
    """All verbatim texts a statement claims to represent."""
    t = [s["force_text"], s["agent"]["name"]]
    for a in s["acts"]:
        t += [a["verb_text"], a["object"]["text"]] + [v["text"] for v in a["slots"].values()]
    t += [it["text"] for it in s["items"]] + [d["text"] for d in s["details"]]
    for c in s["conditions"] + s["exceptions"]:
        _walk_cond_texts(c, t)
    return [x for x in t if x and x.strip()]


def content_mask(etoks):
    """True for tokens that carry meaning (not function words / outline numbers)."""
    ew = [w for w, _, _ in etoks]
    mask = []
    for i, w in enumerate(ew):
        if w in FUNCTION_WORDS:
            mask.append(False)
        elif re.fullmatch(r"\d+", w):
            nxt = ew[i + 1] if i + 1 < len(ew) else ""
            mask.append(nxt in UNITS)
        else:
            mask.append(True)
    return mask


CUES_IN_IGNORED = re.compile(r"\b(shall|must|may|will|not|no|never|unless|except|only|agree\w*|permit\w*|prohibit\w*|"
                             r"obligat\w*|require\w*|disclos\w*|return\w*|destroy\w*|copy|copies)\b", re.I)


TRIGGERS = {"if", "unless", "except", "without", "provided", "upon", "save", "only", "within", "prior", "subject",
            "notwithstanding", "whenever", "where", "until", "before", "after", "during", "nor", "neither", "not", "no"}


def clean_ignored(items):
    """The AI sometimes returns plain strings here; accept them."""
    out = []
    for i in items or []:
        if isinstance(i, str):
            out.append({"text": i, "why": ""})
        elif isinstance(i, dict) and str(i.get("text", "")).strip():
            out.append({"text": str(i["text"]), "why": str(i.get("why", ""))})
    return out


def ledger(evidence, stmts, ignored=()):
    ignored = clean_ignored(ignored)
    """Which content words of the evidence are represented by some slot? Returns
    {covered_pct, orphans:[{word, pos}], flags:[...], n_content}."""
    ev = C.norm(evidence)
    etoks = tokens(ev)
    ew = [w for w, _, _ in etoks]
    mask = content_mask(etoks)
    covered = [False] * len(ew)
    flags = []
    q_ranges = []
    for si, s in enumerate(stmts):
        qr = locate_tokens(s["quote"], ew)
        if not qr:
            flags.append({"type": "ungrounded_quote", "stmt": si, "detail": s["quote"][:100]})
            q_ranges.append(None)
            continue
        q_ranges.append(qr)
        lo, hi = qr[0][0], qr[-1][1]
        own = set()
        for text in _slot_texts(s):
            r = locate_all(text, ew, lo, hi) or locate_tokens(text, ew)
            if not r:
                flags.append({"type": "ungrounded_slot", "stmt": si, "detail": text[:100]})
                continue
            for a, b in r:
                for k in range(a, b):
                    covered[k] = True
                    own.add(k)
        # a statement must itself carry the condition/limit words and content words of ITS OWN quote
        lost = []
        for qa, qb in qr:
            for k in range(qa, qb):
                if k in own:
                    continue
                if (mask[k] or ew[k] in TRIGGERS) and ew[k] not in lost:
                    lost.append(ew[k])
        if lost:
            flags.append({"type": "statement_incomplete", "stmt": si,
                          "detail": "words of this statement's own quote that none of its fields carry: " + " ".join(lost[:20])})
        if not s["force_text"].strip():
            flags.append({"type": "no_force_text", "stmt": si, "detail": "force_text (the modal words) is empty"})
    for ig in ignored:
        r = locate_tokens(ig.get("text", ""), ew)
        if not r:
            flags.append({"type": "ungrounded_ignored", "detail": str(ig.get("text", ""))[:100]}); continue
        for a, b in r:
            for k in range(a, b):
                covered[k] = True
        if CUES_IN_IGNORED.search(ig.get("text", "")):
            flags.append({"type": "ignored_has_cue",
                          "detail": f"'{ig['text'][:80]}' was ignored ({ig.get('why', '?')}) but contains legal wording"})
    orphans = [{"word": ew[k], "pos": etoks[k][1]} for k in range(len(ew)) if mask[k] and not covered[k]]
    n_content = sum(mask)
    pct = 1.0 if not n_content else 1 - len(orphans) / n_content
    if orphans:
        flags.append({"type": "unrepresented_words",
                      "detail": "content words not in any slot: " + " ".join(o["word"] for o in orphans[:25])
                                + (" ..." if len(orphans) > 25 else "")})
    return {"covered_pct": pct, "orphans": orphans, "flags": flags, "n_content": n_content}


# =============================================================================== semantic audits
NEG_CUE = re.compile(r"\b(shall|will|may|must|can|agrees?|undertakes?)\s+not\b|\bagrees?\s+not\s+to\b|\bnot\s+(be\s+)?(permitted|allowed)\b|"
                     r"\bprohibit\w*|\bneither\b|\bnor\b|\bno\s+(other\s+)?(right|license|licence)\b|\bnot\s+for\s+any\b|"
                     r"\bwithout\s+(the\s+)?(prior\s+|express\s+|written\s+)", re.I)
OBL_CUE = re.compile(r"\b(shall|must|will|agrees?\s+to|required\s+to|undertakes?|obligat\w*)\b", re.I)
PERM_CUE = re.compile(r"\b(may|permitted|allowed|entitled|free\s+to|can|not\s+apply|not\s+be\s+(restricted|prevented|precluded|in\s+breach|liable))\b", re.I)
EXEMPT_CUE = re.compile(r"\b(not\s+apply|do(es)?\s+not\s+apply|exclud\w*|exempt\w*|not\s+be\s+(restricted|prevented|precluded|prohibited|in\s+breach|liable|deemed\s+to\s+(have\s+)?breach\w*)|"
                        r"no\s+obligation|not\s+(be\s+)?required\s+to|neither\s+\w+\s+(will|shall)\s+be\s+required|free\s+to|neither\s+\w+\s+(will|shall)\s+be\s+(restricted|prevented|precluded|prohibited)|"
                        r"nothing\s+in\s+this\s+agreement\s+(shall\s+)?(prevent|restrict|prohibit)\w*|"
                        r"shall\s+not\s+(be\s+)?(restricted|prevented|precluded|limited)|shall\s+not\s+(include|cover|extend\s+to))\b", re.I)
EXC_START = re.compile(r"^\s*(except|unless|other than)\b", re.I)
COND_START = re.compile(r"^\s*(provided|if|only if|upon|within|to the extent|who have|having)\b", re.I)
WITHOUT_VERBING = re.compile(r"\bwithout\s+(retaining|keeping|making|copying|reproducing|disclosing|using|storing|"
                             r"preserving|archiving|duplicating)\b", re.I)

SEED_VERBS = {
    "copy": "CreateCopy", "reproduce": "CreateCopy", "duplicate": "CreateCopy", "reprint": "CreateCopy",
    "photocopy": "CreateCopy", "replicate": "CreateCopy", "retain": "RetainCopies", "keep": "RetainCopies",
    "solicit": "SolicitRepresentatives", "recruit": "SolicitRepresentatives", "hire": "SolicitRepresentatives",
    "disassemble": "ReverseEngineer", "decompile": "ReverseEngineer", "reverse": "ReverseEngineer",
    "destroy": "ReturnOrDestroy", "return": "ReturnOrDestroy", "erase": "ReturnOrDestroy", "redeliver": "ReturnOrDestroy",
}


def semantic_audit(stmts, evidence):
    flags = []
    for i, s in enumerate(stmts):
        q = s["quote"]
        for c in s["conditions"] + s["exceptions"]:       # judge the modal wording, not the carve-out's wording
            if c["text"]:
                q = re.sub(re.escape(c["text"]), " ", q, flags=re.I)
        ctx = q + " " + s["force_text"]
        f = s["force"]
        if s.get("inferred"):
            flags.append({"type": "inferred_statement", "stmt": i, "level": "info",
                          "detail": "meaning is implied rather than stated; a human should confirm"})
            continue
        neg, obl, perm, exempt = NEG_CUE.search(ctx), OBL_CUE.search(ctx), PERM_CUE.search(ctx), EXEMPT_CUE.search(ctx)
        if f in ("permission", "obligation") and neg and not exempt and not WITHOUT_VERBING.search(q):
            if not (f == "permission" and not NEG_CUE.search(s["force_text"])):
                flags.append({"type": "modality_mismatch", "stmt": i,
                              "detail": f"wording has a negative cue ('{neg.group(0)}') but force is {f}"})
        if f == "prohibition" and exempt:
            flags.append({"type": "exemption_read_as_prohibition", "stmt": i,
                          "detail": f"'{exempt.group(0)}' is an exemption/permission wording but force is prohibition "
                                    f"(\"not restricted\", \"not in breach\", \"shall not apply\" => PERMISSION)"})
        if f == "prohibition" and not neg and not WITHOUT_VERBING.search(ctx) and not re.search(r"\b(only|solely|sole|limit\w*|restrict\w*|except|no\s+event)\b", ctx, re.I):
            flags.append({"type": "modality_mismatch", "stmt": i, "detail": "prohibition, but wording has no negative/restrictive cue"})
        if f == "obligation" and perm and not obl:
            flags.append({"type": "modality_mismatch", "stmt": i, "detail": "obligation, but wording only says 'may'"})
        if f == "permission" and obl and not perm and not exempt:
            flags.append({"type": "modality_mismatch", "stmt": i, "detail": "permission, but wording says 'shall'"})
        for c in s["conditions"]:
            if EXC_START.match(c["text"]):
                flags.append({"type": "exception_as_condition", "stmt": i, "detail": f"condition starts like an exception: '{c['text'][:70]}'"})
        for c in s["exceptions"]:
            if COND_START.match(c["text"]):
                flags.append({"type": "condition_as_exception", "stmt": i, "detail": f"exception starts like a condition: '{c['text'][:70]}'"})
        if f == "prohibition" and re.search(r"\bexcept\b", q, re.I) and s["conditions"] and not s["exceptions"]:
            flags.append({"type": "exception_as_condition", "stmt": i, "detail": "quote says 'except' but the carve-out is recorded as a condition"})
        # 'without retaining/keeping/making ... copies' is a prohibition of its own
        if WITHOUT_VERBING.search(q) and f in ("obligation", "permission"):
            m = WITHOUT_VERBING.search(q)
            has = any(a["verb"] in ("retain", "keep", "store", "preserve", "archive", "copy", "reproduce", "disclose", "use", "make", "duplicate")
                      for st in stmts if st["force"] == "prohibition" for a in st["acts"])
            if not has:
                flags.append({"type": "without_clause_missing_prohibition", "stmt": i,
                              "detail": f"'{m.group(0)}' states a prohibition of its own; add a prohibition statement"})
        for c in s["conditions"] + s["exceptions"]:
            alts = len(re.findall(r"\bor\b", c["text"]))
            if len(c["text"]) > 140 and alts >= 3 and "any" not in c and "all" not in c:
                flags.append({"type": "compressed_condition", "stmt": i,
                              "detail": f"one atom stands for {alts + 1}+ alternatives; use an 'any' condition with one leaf each"})
    return flags


# =============================================================================== English rendering (deterministic)
def _w(p):
    return C.words(p) if re.search(r"[a-z][A-Z]", p) else p.replace("_", " ")


def render_cond(c):
    if "any" in c:
        return "(" + " OR ".join(render_cond(k) for k in c["any"]) + ")"
    if "all" in c:
        return "(" + " AND ".join(render_cond(k) for k in c["all"]) + ")"
    return f"[{c['text']}]"


def _act_text(a):
    bits = [a["verb"].replace("_", " ") + (f" (\"{a['verb_text']}\")" if a["verb_text"] and a["verb_text"].lower() != a["verb"] else "")]
    if a["object"]["text"]:
        bits.append("object: \"" + a["object"]["text"] + "\"")
    bits += [f"{k}: \"{v['text']}\"" for k, v in a["slots"].items()]
    return " | ".join(bits)


def render(s):
    """Plain-English reading of EVERYTHING recorded for a statement. No AI."""
    f = s["force"]
    who = f"{_w(s['agent']['role'])}" + (f" (\"{s['agent']['name']}\")" if s["agent"]["name"] else "")
    head = {"obligation": "MUST", "prohibition": "MUST NOT", "permission": "MAY", "fact": "STATES"}.get(f)
    if f in ("obligation", "prohibition", "permission", "fact"):
        acts = []
        for a in s["acts"]:
            acts.append(_act_text(a))
        core = f"{who} {head} (\"{s['force_text']}\"): " + "  ;  ".join(acts)
    elif f in ("includes", "excludes"):
        its = ", ".join(f"\"{i['text']}\"" + (f" [{'/'.join(i['classes'])}]" if i["classes"] else "") for i in s["items"])
        core = f"{who} {'INCLUDES' if f == 'includes' else 'EXCLUDES'}" + (" (exhaustive)" if s["exhaustive"] else "") + f": {its}"
    else:
        core = f"{who}: obligations SURVIVE termination (\"{s['force_text']}\")"
    if s.get("details"):
        core += "  [" + "; ".join(f"{d['slot']}: \"{d['text']}\"" for d in s["details"]) + "]"
    if s["conditions"]:
        core += "  -- ONLY IF " + " AND ".join(render_cond(c) for c in s["conditions"])
    if s["exceptions"]:
        core += "  -- UNLESS " + " OR ".join(render_cond(c) for c in s["exceptions"])
    return core


# =============================================================================== flatten + compile to Narsese
def _roles(role):
    return ["ReceivingParty", "DisclosingParty"] if role == "BothParties" else [role]


def _dnf(c):
    """Condition -> list of alternatives; each alternative is a list of leaf atoms."""
    if "any" in c:
        return [alt for k in c["any"] for alt in _dnf(k)]
    if "all" in c:
        alts = [[]]
        for k in c["all"]:
            alts = [a + b for a in alts for b in _dnf(k)]
        return alts
    return [[c["atom"]]]


def _and_dnf(conds):
    alts = [[]]
    for c in conds:
        alts = [a + b for a in alts for b in _dnf(c)]
    return alts


def nest(op, parts):
    """ONA keeps only the FIRST TWO components of any compound ((*, a, b, c) is read as (a * b)). So every product / conjunction / disjunction
    is written as BINARY pairs. They are BALANCED ((*, (*, a, b), (*, c, d))) and not chained, because ONA stores a term as a binary tree in a
    fixed array: a chain of n pairs needs 2^n slots, a balanced tree only log2(n) levels. Nothing is lost."""
    parts = list(parts)
    if len(parts) == 1:
        return parts[0]
    m = len(parts) // 2
    return f"({op}, {nest(op, parts[:m])}, {nest(op, parts[m:])})"


def conj_tree(ps):
    """A conjunction of >2 statements as a balanced tree of binary conjunctions, plus the inner conjunctions that ONA must be told hold
    (it does not compose them by itself): -> (term, [(inner_term, [leaf, ...]), ...])"""
    ps = list(ps)
    if len(ps) == 1:
        return ps[0], []
    if len(ps) == 2:
        return f"(&&, {ps[0]}, {ps[1]})", []
    m = len(ps) // 2
    L, pl = conj_tree(ps[:m]); R, pr = conj_tree(ps[m:])
    prem = pl + pr
    if m > 1: prem.append((L, ps[:m]))
    if len(ps) - m > 1: prem.append((R, ps[m:]))
    return f"(&&, {L}, {R})", prem


def _id(x):
    return re.sub(r"[^A-Za-z0-9]", "", x) or "X"


def _detail_args(s):
    return [f"{d['slot']}_{_id(d['term'])}" for d in s.get("details", [])]


def rich_arglist(role, a, extra=()):
    args = [_id(role), _id(a["verb"])]
    if a["object"]["text"]:
        args.append("object_" + _term(None, a["object"]["text"], 8))
    for k in SLOTS:
        if k in a["slots"]:
            args.append(f"{k}_" + _id(a["slots"][k]["term"]))
    return args + list(extra)


def rich_args(role, a, extra=()):
    """The WHOLE act as one Narsese tuple: role, verb, object, every filled slot (tagged by slot name) and the statement's details."""
    args = [_id(role), _id(a["verb"])]
    if a["object"]["text"]:
        args.append("object_" + _term(None, a["object"]["text"], 8))
    for k in SLOTS:
        if k in a["slots"]:
            args.append(f"{k}_" + _id(a["slots"][k]["term"]))
    return nest("*", args + list(extra))


MODAL = {"obligation": "MUST", "prohibition": "MUST NOT", "permission": "MAY"}


def flatten(stmts):
    """-> units: one per (statement, act-or-item, role). Each unit carries its full Narsese tuple (`rich`) and a plain-English `desc`.
    Nothing here knows any hypothesis."""
    units = []
    for si, s in enumerate(stmts):
        f = s["force"]
        det = _detail_args(s)
        for role in _roles(s["agent"]["role"]):
            base = {"stmt": si, "role": role, "conds": s["conditions"], "excs": s["exceptions"], "relation": None, "why": "",
                    "exhaustive": s["exhaustive"]}
            if f in ("obligation", "prohibition", "permission"):
                for ai, a in enumerate(s["acts"]):
                    units.append({**base, "act": ai, "item": None, "pred": FORCE_PRED[f], "kind": "act",
                                  "rich": rich_args(role, a, det), "args": rich_arglist(role, a, det), "desc": f"{role} {MODAL[f]} {_act_text(a)}"})
            elif f in ("includes", "excludes"):      # "excludes" ("does not include X") was silently dropped before: it is now a unit too
                for ii, it in enumerate(s["items"]):
                    units.append({**base, "act": None, "item": ii, "pred": FORCE_PRED[f], "kind": "item",
                                  "rich": nest("*", [_id(role), "item_" + _id(it["term"])] + det), "args": [_id(role), "item_" + _id(it["term"])] + det,
                                  "desc": f"{role} {f.upper()} \"{it['text']}\""})
            elif f == "survival":
                units.append({**base, "act": None, "item": None, "pred": "Survives", "kind": "survival",
                              "rich": nest("*", [_id(role), "survive"] + det), "args": [_id(role), "survive"] + det,
                              "desc": f"{role}: {s['agent']['name'] or 'obligations'} SURVIVE (\"{s['force_text']}\")"})
    return units


def T(a, x, p):
    return f"<(*, {a}, {x}) --> {p}>"


def HT(role, x):
    """A condition leaf as <Role_Atom --> Holds>: one term level shallower than a (*, role, atom) pair, so deep
    AND/OR trees still fit the 128-slot ONA build that macOS can start."""
    return f"<{role}_{x} --> Holds>"


def transfers(rel, pred, kind):
    """May a contract statement (this modality, this relation to the hypothesis) be asserted AS the hypothesis statement?"""
    if rel not in ("same", "kind_of", "broader"):
        return False
    if kind == "item":
        return pred == "Includes"          # a covered item shows the hypothesis' kind of information is covered
    if kind == "survival":
        return rel == "same"
    if rel == "same":
        return True
    if rel == "kind_of":                   # one specific way of doing it: permission / obligation carry over, a ban does not
        return pred in ("Permitted", "Obligated")
    return pred == "Prohibited"            # broader: forbidding the wider act forbids the narrower one


def cond_term(c, role):
    """A condition as ONE Narsese term that keeps its OR / AND structure: (||, <..Holds>, <..Holds>), (&&, ...) or a single <..Holds>."""
    if "any" in c:
        return nest("||", [cond_term(k, role) for k in c["any"]])
    if "all" in c:
        return nest("&&", [cond_term(k, role) for k in c["all"]])
    return HT(role, c.get("atom") or _term(None, c.get("text", ""), 5))


def hypothesis_from_stmt(s):
    """A translated hypothesis -> the single Narsese statement it is asking about: {"tuple", "pred", "desc"}."""
    units = flatten([s])
    if not units:
        return None
    u = units[0]
    tup = u["rich"]
    args = list(u["args"])
    pred = "OnlyIncludes" if (u["kind"] == "item" and s["exhaustive"]) else u["pred"]
    whens = [cond_term(c, u["role"]) for c in s["conditions"]]
    defs = []
    if whens:
        tup = nest("*", args + whens)
        # a deep AND/OR condition inside the conclusion does not fit the 128-slot ONA build that macOS can start. Then the
        # composite is NAMED by a condition atom, and its full structure is kept in a definition line <(||, ...) ==> <Name --> Holds>>.
        import a2_ona as _O
        for i, w in enumerate(whens):
            if _O.slots_needed(f"<<x --> Holds> ==> <{tup} --> {pred}>>") <= _O.build_limit() - 1 or not w.startswith(("(||", "(&&")):
                continue
            leaves = re.findall(r"<(\w+)_(\w+) --> Holds>", w)
            op = "Or" if w.startswith("(||") else "And"
            name = f"{u['role']}_when" + op + "".join(a[:14] for _, a in leaves)
            atom = f"<{name} --> Holds>"
            defs.append(f"<{w} ==> {atom}>.")
            whens[i] = atom
            tup = nest("*", args + whens)
    return {"tuple": tup, "pred": pred, "desc": render(s), "n_units": len(units), "defs": defs}


CONSENT = re.compile(r"\b(consent|authori[sz]\w*|approv\w*|permission|agree(s|d|ment)?\s+(in\s+writing|of)|waiv\w*)\b", re.I)


def _cond_text(c):
    acc = []
    _walk_cond_texts(c, acc)
    return " ".join(acc)


def _live(u):
    return transfers(u["relation"], u["pred"], u["kind"])


def implied_permissions(units):
    """An exception that names a real circumstance ("except as required for the Transaction") means the action IS
    permitted in that circumstance => derive a Permitted unit. An exception that is only the OTHER party's consent
    or authorisation is not a circumstance the recipient can rely on, so it derives nothing (policy, see README)."""
    out = []
    for u in units:
        if u["pred"] != "Prohibited" or u["kind"] != "act" or u["relation"] not in ("same", "kind_of", "broader"):
            continue
        for e in u["excs"]:
            if CONSENT.search(_cond_text(e)):
                continue
            out.append({**u, "pred": "Permitted", "conds": [e], "excs": [], "derived_from": "exception"})
    return units + out


def link_carveouts(units):
    """A specific permission on the same act becomes an exception of the general prohibition (both aligned to the same hypothesis)."""
    units = implied_permissions(copy.deepcopy(units))
    links = []
    for pi, p in enumerate(units):
        if p["pred"] != "Prohibited" or p["kind"] != "act" or not _live(p):
            continue
        for qi, q in enumerate(units):
            if q["pred"] != "Permitted" or q["kind"] != "act" or not _live(q) or q["role"] != p["role"]:
                continue
            if q["stmt"] == p["stmt"] and not q.get("derived_from"):
                continue
            alts = _and_dnf(q["conds"]) if q["conds"] else [[f"CarveOut{q['stmt']}"]]
            for alt in alts:
                atom = alt[0] if len(alt) == 1 else "And".join(alt)
                p["excs"] = p["excs"] + [{"text": "(carve-out permitted elsewhere)", "atom": atom, "linked": True}]
            links.append((p["stmt"], q["stmt"]))
    return units, sorted(set(links))


def _emit_rule(role, conds, excs, concl, ui, base, extra, seen, cond_names, pre=()):
    """concl holds if all `conds` hold and no `excs` holds (and the `pre` statements hold)."""
    exc_atoms = []
    for e in excs:
        for alt in _dnf(e):
            if len(alt) == 1:
                exc_atoms.append(alt[0])
            else:
                comb = "And".join(alt)
                exc_atoms.append(comb)
                lhs, prem = conj_tree([HT(role, a) for a in alt])
                ln = f"<{lhs} ==> {HT(role, comb)}>."
                if ln not in seen:
                    seen.add(ln); base.append((ln, ui))
                for term, leaves in prem:                      # inner conjunctions ONA must be told about (all leaves are assumed true only if all atoms are conditions)
                    if all(a in cond_names for a in alt) and f"{term}." not in seen:
                        seen.add(f"{term}."); extra.append((f"{term}.", ui))
    alts = _and_dnf(conds)
    if len(alts) > 1:
        # several alternative conditions ("if A, or B, or C"): name them ONCE (3 small rules <A ==> AnyOf>, <B ==> AnyOf>, ...) and let every
        # conclusion use that name. Repeating the full rule per alternative made a 30-item definition 3x bigger and ONA too slow to answer.
        name = "AnyOf_" + "_".join(a[:12] for alt in alts for a in alt[:1])
        for alt in alts:
            if len(alt) == 1:
                lhs, prem = HT(role, alt[0]), []
            else:
                lhs, prem = conj_tree([HT(role, a) for a in alt])
            ln = f"<{lhs} ==> {HT(role, name)}>."
            if ln not in seen:
                seen.add(ln); base.append((ln, ui))
            for term, leaves in prem:
                if all(a in cond_names for a in alt) and f"{term}." not in seen:
                    seen.add(f"{term}."); extra.append((f"{term}.", ui))
            for a in alt:
                if a in cond_names and f"{HT(role, a)}." not in seen:
                    seen.add(f"{HT(role, a)}."); extra.append((f"{HT(role, a)}.", ui))
        alts = [[name]]
        cond_names = set(cond_names) | {name}
        cond_names.discard(None)
    for alt in alts:
        ants = list(pre) + [HT(role, a) for a in alt] + [f"(--, {HT(role, a)})" for a in exc_atoms]
        if not ants:
            line = f"{concl}."
        else:
            lhs, prem = conj_tree(ants)
            line = f"<{lhs} ==> {concl}>."
            holds = set(pre) | {HT(role, a) for a in alt} | \
                {f"(--, {HT(role, a)})" for a in exc_atoms if a not in cond_names and not a.startswith("CarveOut")}
            for term, leaves in prem:
                if all(l in holds for l in leaves) and f"{term}." not in seen:
                    seen.add(f"{term}."); extra.append((f"{term}.", ui))
            for a in alt + exc_atoms:
                t = HT(role, a)
                l2 = f"{t}." if ((a in cond_names) or a.startswith("CarveOut")) else f"(--, {t})."
                if l2 not in seen:
                    seen.add(l2); extra.append((l2, ui))
        if line not in seen:
            seen.add(line); base.append((line, ui))


def _conclusion(u, hyp):
    """The hypothesis statement (or its denial) this unit supports, or None."""
    t, hp = hyp["tuple"], hyp["pred"]
    if u["kind"] == "item":
        rel, covers = u["relation"], u["relation"] in ("same", "kind_of", "broader")
        if u["pred"] == "Excludes":
            # the definition says the item is NOT confidential information: the claim that it is included is false, a claim that it is
            # excluded is true, and (policy, as for exceptions) the recipient may then do with it what the hypothesis asks (a permission)
            if not covers:
                return None
            return {"Includes": f"(--, <{t} --> Includes>)", "Excludes": f"<{t} --> Excludes>",
                    "Permitted": f"<{t} --> Permitted>"}.get(hp)
        if hp == "Includes" and covers:
            return f"<{t} --> Includes>"
        if hp == "Excludes" and covers:
            return f"(--, <{t} --> Excludes>)"
        if hp == "OnlyIncludes" and rel in ("outside", "broader", "unrelated"):   # anything beyond the category => "only" is false
            return f"(--, <{t} --> OnlyIncludes>)"
        return None
    if u["relation"] == "conflicts":
        # a duty that cannot be met while doing the hypothesis act ('must return and destroy' vs 'may retain'): the permission is denied
        return f"(--, <{t} --> Permitted>)" if (u["pred"] == "Obligated" and hp == "Permitted" and _live(u)) else None
    return f"<{t} --> {u['pred']}>" if _live(u) else None


def compile_units(units, hyp):
    """-> (base, extra): lists of (narsese_line, unit_index). `extra` = lenient-mode assumptions about condition atoms.
    For every unit: (1) the act as ONE full statement, (2) if aligned to the hypothesis, a bridge and a direct rule to the hypothesis statement."""
    base, extra, seen = [], [], set()
    cond_names = {a for u in units for alt in _and_dnf(u["conds"]) for a in alt}
    for ui, u in enumerate(units):
        rich_head = f"<{u['rich']} --> {u['pred']}>"
        _emit_rule(u["role"], u["conds"], u["excs"], rich_head, ui, base, extra, seen, cond_names)
        concl = _conclusion(u, hyp)
        if concl:
            br = f"<{rich_head} ==> {concl}>."
            if br not in seen:
                seen.add(br); base.append((br, ui))
            _emit_rule(u["role"], u["conds"], u["excs"], concl, ui, base, extra, seen, cond_names)
    # an exhaustive definition ("means ...") whose every item lies inside the hypothesis' category: the hypothesis' "only includes" holds
    if hyp["pred"] == "OnlyIncludes":
        by_stmt = {}
        for ui, u in enumerate(units):
            if u["kind"] == "item" and u["pred"] == "Includes":
                by_stmt.setdefault((u["stmt"], u["role"]), []).append(ui)
        for (si, role), uis in by_stmt.items():
            if all(units[i]["relation"] in ("same", "kind_of") for i in uis) and units[uis[0]].get("exhaustive"):
                pre = [f"<{units[i]['rich']} --> Includes>" for i in uis]
                u0 = units[uis[0]]
                _emit_rule(role, u0["conds"], u0["excs"], f"<{hyp['tuple']} --> OnlyIncludes>", uis[0], base, extra, seen, cond_names, pre)
    return base, extra


def detail_lines(stmts):
    """The part of the meaning that does not gate the verdict but IS in the knowledge base: every verb, object,
    recipient, purpose, manner, time, place, item, and condition frame becomes a queryable Narsese relation."""
    out = []
    S = lambda x: re.sub(r"[^A-Za-z0-9]", "", x) or "X"
    for si, s in enumerate(stmts):
        sid = f"s{si}"
        out.append((f"<{sid} --> [{s['force']}]>.", si))
        out.append((f"<(*, {sid}, {S(s['agent']['role'])}) --> Agent>.", si))
        for ai, a in enumerate(s["acts"]):
            aid = f"{sid}a{ai}"
            out.append((f"<(*, {sid}, {aid}) --> Act>.", si))
            out.append((f"<(*, {aid}, {S(a['verb'])}) --> Verb>.", si))
            if a["maps_to"]:
                out.append((f"<(*, {aid}, {a['maps_to']}) --> CountsAs>.", si))
            if a["object"]["text"]:
                out.append((f"<(*, {aid}, {_term(None, a['object']['text'])}) --> Object>.", si))
            for k, v in a["slots"].items():
                out.append((f"<(*, {aid}, {S(v['term'])}) --> {k.capitalize()}>.", si))
        for it in s["items"]:
            out.append((f"<(*, {sid}, {S(it['term'])}) --> Item>.", si))
        for d in s["details"]:
            out.append((f"<(*, {sid}, {S(d['term'])}) --> {d['slot'].title().replace('_','')}>.", si))
        def cond_rel(c, kind, ci=[0]):
            ci[0] += 1
            cid = f"{sid}c{ci[0]}"
            out.append((f"<(*, {sid}, {cid}) --> {kind}>.", si))
            for k in ("any", "all"):
                for kid in c.get(k, []):
                    ci2 = cond_rel(kid, kind="Part")
                    out.append((f"<(*, {cid}, {ci2}) --> {k.capitalize()}Of>.", si))
            fr = c.get("frame") or {}
            for k, v in fr.items():
                out.append((f"<(*, {cid}, {S(v)}) --> {k.capitalize()}>.", si))
            if c.get("atom"):
                out.append((f"<(*, {cid}, {S(c['atom'])}) --> Atom>.", si))
            return cid
        for c in s["conditions"]:
            cond_rel(c, "Condition")
        for c in s["exceptions"]:
            cond_rel(c, "Exception")
    return out


AXIOMS = [
    ("AX1", "If an action is permitted, it is not prohibited.", "<<$x --> Permitted> ==> (--, <$x --> Prohibited>)>."),
    ("AX2", "If an action is prohibited, it is not permitted.", "<<$x --> Prohibited> ==> (--, <$x --> Permitted>)>."),
    ("AX3", "If an action is obligatory, it is permitted.", "<<$x --> Obligated> ==> <$x --> Permitted>>."),
    ("AX4", "If an action is obligatory, it is not prohibited.", "<<$x --> Obligated> ==> (--, <$x --> Prohibited>)>."),
    ("AX5", "If an action is prohibited, it is not obligatory.", "<<$x --> Prohibited> ==> (--, <$x --> Obligated>)>."),
]
AX_LINES = [(a[2], None) for a in AXIOMS]

"""Run ONA and parse the answer, including which input lines the answer was derived from."""
import os, re, subprocess

ONA_PATH = os.environ.get("ONA_PATH", os.path.expanduser("~/Downloads/OpenNARS-for-Applications"))
CYCLES = 50


NAME_MAX = 31          # ONA's default ATOMIC_TERM_LEN_MAX is 32: longer names are silently CUT, so two different long names can become the same atom


def _short(name):
    import hashlib
    return name if len(name) <= NAME_MAX else name[:NAME_MAX - 7] + "_" + hashlib.md5(name.encode()).hexdigest()[:6]


def shorten_names(line):
    """Give every name longer than ONA's limit a unique, stable short form (prefix + hash). Short names are untouched."""
    return re.sub(r"[A-Za-z0-9_]{%d,}" % (NAME_MAX + 1), lambda m: _short(m.group(0)), line)


def run(belief_lines, query, cycles=CYCLES):
    """belief_lines: list of Narsese strings (beliefs, in order). query: one Narsese '?' string.
    Returns {"frequency", "confidence", "used": [1-based indices into belief_lines], "raw"}."""
    nar = os.path.join(ONA_PATH, "NAR")
    if not os.path.exists(nar):
        raise FileNotFoundError(f"ONA binary not found at {nar}. Set ONA_PATH (env var) to your ONA folder.")
    belief_lines = [shorten_names(l) for l in belief_lines]
    query = shorten_names(query)
    # ONA's time grows steeply with the number of beliefs, while the answer is already stable after a few cycles (checked: a 54-line
    # knowledge base gives the same frequency at 5, 10, 20 and 50 cycles, in 15 s instead of 100 s). So big knowledge bases get fewer cycles.
    n = len(belief_lines)
    if n > 40:
        cycles = min(cycles, 10)
    timeout = max(60, min(900, 6 * n))
    text = "\n".join(belief_lines + [query]) + f"\n{cycles}\n"
    try:
        p = subprocess.run([nar, "shell"], input=text, capture_output=True, text=True, timeout=timeout)
        out = p.stdout
        if p.returncode != 0 and "Answer:" not in out:
            if p.returncode == 1 and out.strip():
                # ONA's own assertion ("Too many terms for NAR", "...SIZE_MAX too small"): the knowledge base does not fit this build
                msg = [l for l in out.splitlines() if l.strip()][-2:]
                return {"frequency": None, "confidence": None, "used": [], "raw": out, "dropped": 1,
                        "error": " | ".join(msg)[:300]}
            raise RuntimeError(f"ONA crashed (exit code {p.returncode}) at {nar}: {p.stderr[:300]}")   # a crash must never look like "no answer"
    except subprocess.TimeoutExpired:      # a very large knowledge base: report "no answer" instead of crashing
        return {"frequency": None, "confidence": None, "used": [], "raw": "TIMEOUT"}
    dropped = count_dropped(belief_lines)           # statements too big for this ONA build are silently dropped by ONA
    answers = [l for l in out.splitlines() if l.startswith("Answer:")]
    if not answers:
        return {"frequency": None, "confidence": None, "used": [], "raw": out, "dropped": dropped}
    last = answers[-1]
    m = re.search(r"frequency=([\d.]+),\s*confidence=([\d.]+)", last)
    st = re.search(r"Stamp=\[([\d,\s]*)\]", last)
    used = sorted(int(x) for x in st.group(1).split(",") if x.strip()) if st else []
    if not m:
        return {"frequency": None, "confidence": None, "used": [], "raw": out, "dropped": dropped}
    return {"frequency": float(m.group(1)), "confidence": float(m.group(2)), "used": used, "raw": out, "dropped": dropped}


def label_from_frequency(freq):
    """Paper thresholds: >=0.50 true, <=0.05 false, otherwise (or no answer) uncertain."""
    if freq is None:
        return "NotMentioned"
    if freq >= 0.50:
        return "Entailment"
    if freq <= 0.05:
        return "Contradiction"
    return "NotMentioned"


def check_build():
    """True if this ONA build accepts the size of statement the pipeline writes (an 8-part tuple inside an implication)."""
    def bal(a):
        return a[0] if len(a) == 1 else f"(*, {bal(a[:len(a) // 2])}, {bal(a[len(a) // 2:])})"
    X, Y = bal([f"x{i}" for i in range(8)]), bal([f"y{i}" for i in range(8)])
    line = f"<(&&, <{X} --> P>, <c --> H>) ==> <{Y} --> P>>."
    r = run([line], "<a --> b>?", cycles=1)
    return r.get("dropped", 1) == 0


# ---- size check that does not depend on ONA's output format -------------------------------------------------
def _parse(t, i=0):
    """Narsese term -> nested tuples (op, children...) / atom string; returns (node, next_index)."""
    while t[i] == " ":
        i += 1
    if t[i] == "<":
        a, i = _parse(t, i + 1)
        while t[i] == " ": i += 1
        m = re.match(r"(-->|==>|<->|<=>|=/>|=\|>|</>)", t[i:])
        op = m.group(1); i += len(op)
        b, i = _parse(t, i)
        while t[i] == " ": i += 1
        return (op, a, b), i + 1                  # skip '>'
    if t[i] == "(":
        j = t.index(",", i)
        op = t[i + 1:j].strip(); i = j + 1
        kids = []
        while True:
            k, i = _parse(t, i)
            kids.append(k)
            while t[i] == " ": i += 1
            if t[i] == ",": i += 1; continue
            if t[i] == ")": i += 1; break
        return (op, *kids), i
    m = re.match(r"[A-Za-z0-9_$#\[\]{}\.]+", t[i:])
    return m.group(0), i + len(m.group(0))


def slots_needed(line):
    """How many slots of ONA's fixed term array this statement needs (a term is a binary tree stored heap-style: children of i are 2i+1, 2i+2)."""
    body = re.split(r"[.?!]\s*(?:\{|$)", line.strip().rstrip("."), 1)[0].strip() if False else line.strip().rstrip(".?! ")
    node, _ = _parse(body)
    def walk(n, idx):
        if isinstance(n, str):
            return idx
        m = idx
        kids = n[1:]
        if n[0] == "--":                      # negation has one child
            return walk(kids[0], 2 * idx + 1)
        for c, k in enumerate(kids[:2]):
            m = max(m, walk(k, 2 * idx + 1 + c))
        return m
    return walk(node, 0) + 1


def build_limit():
    cfg = os.path.join(ONA_PATH, "src", "Config.h")
    try:
        m = re.search(r"#define\s+COMPOUND_TERM_SIZE_MAX\s+(\d+)", open(cfg).read())
        return int(m.group(1)) if m else 64
    except OSError:
        return 64


def count_dropped(lines):
    """Number of fed statements that need more term slots than this ONA build has (computed, so it does not depend on ONA's output format)."""
    lim = build_limit(); n = 0
    for l in set(lines):
        if not l.strip() or l.strip().isdigit():
            continue
        try:
            if slots_needed(l) > lim:
                n += 1
        except Exception:
            pass
    return n

"""protocol_stub.py — a member's CANCEL rules generated from its own rules (specialist-tree s-404d001f step 3c, the
architect's v8 §13.2 and rulings on the draft; spec/15 amendment 7): a stop is a cancel — the director's
tick__cancel(D) takes D's goal (a revoke takes the body and keeps it), and the member drops the goal itself. No
world's names in here: the member's rules and its manifest's goal kinds say everything.

The states a member can hold while it works are walked from what takes its goal:
- a member with the protocol stub's idle/busy (the tree's begin rules): from every rule that consumes idle (begin_K,
  and a member's own trigger, MiniHack act's guard), its state the tokens it puts out and the goal it reads;
- the task (no idle): from every rule that consumes a goal kind (fetch, reach).
A state is the set of TRACKED tokens: the goal kinds and the member's private linear tokens that a rule consuming a
tracked token (or idle) puts out — a marker a rule puts out from the world alone (act's braced) is no state. A rule
whose tracked body the state (with the goal kinds, which may arrive at any time) covers moves it on; one giving back
idle or putting out an end ends it. The minimal states (a bigger one's cancel would race a smaller one's: the sampled
order) get one rule each, consuming all of it with the cancel:
    cancel_<tokens> [dyn] : tick__cancel(D) * busy * goto(X0) -o idle.      (one = the unit, for the task)
and a member with idle gets cancel_none, `idle * tick__cancel(D) -o idle`: the real race where the member's done and
the stop land in one director beat (path_pop and stop_cancel both enabled, the sampled order) — not for idle members
in general, who get no cancel.

    cancel_rules(text, member, goal_kinds, ends=(), decls="") → [line…]   (doc line + rule, in pairs)

It refuses (StubError, by name): a member whose goal kinds reach no state (no rule takes the goal: nothing a cancel
could drop — a wrong goal kind, or a member with no begin), and a tracked token whose arity neither the base nor
the family package declares.
"""
import re


class StubError(ValueError):
    """A member the generator cannot write a cancel stub for."""

RULE = re.compile(r"^\s+(\w+) \[dyn\] : (.*) -o (.*?)\s*(?:@w [^.]*)?\.(\s*%.*)?$")
PRED = re.compile(r"^pred (\w+)(?:\(([^)]*)\))?\s*:\s*(\w+)\s*\.")


def _atoms(side):
    out = []
    for a in side.split("*"):
        a = a.strip()
        if not a or "<>" in a or a in ("()", "one"):
            continue
        read = a.startswith("$")
        a = a.lstrip("$")
        out.append((a.split("(")[0], read))
    return out


def rules(text):
    """[(name, [(pred, read)…] body, [pred…] head)] of TEXT's [dyn] rules."""
    out = []
    for line in text.splitlines():
        m = RULE.match(line)
        if m:
            out.append((m.group(1), _atoms(m.group(2)), [p for p, _ in _atoms(m.group(3))]))
    return out


def arities(text):
    return {m.group(1): len([a for a in (m.group(2) or "").split(",") if a.strip()])
            for m in (PRED.match(l.strip()) for l in text.splitlines()) if m}


def private(text, member):
    """The preds TEXT declares in MEMBER's own namespace."""
    return {m.group(1) for m in (PRED.match(l.strip()) for l in text.splitlines()) if m and m.group(3) == member}


def states(text, member, goal_kinds, ends=(), crossing=()):
    """The sets of tracked tokens MEMBER can hold while it works, the minimal ones (sorted tuples, sorted): a rule
    that gives back idle or puts out an end (ENDS: the task's done, stuck) ends the work; a state that holds a smaller
    one is left out — its cancel would race the smaller's in the sampled order (one cancel, one rule)."""
    rs = rules(text)
    idle = "idle" in private(text, member)
    goals = set(goal_kinds)
    own = private(text, member) - {"idle"} - goals - set(crossing)   # a crossing pred is no member's own state
    tracked = set(goals) | ({"busy"} if idle else set())
    for _, body, head in rs:                      # a token put out by a rule that consumes what is tracked (or idle)
        if any(not r and (p in tracked or p == "idle") for p, r in body):
            tracked |= {p for p in head if p in own}
    for _ in range(4):                            # … and by the rules that consume those
        for _, body, head in rs:
            if any(not r and p in tracked for p, r in body):
                tracked |= {p for p in head if p in own}
    start = []
    for _, body, head in rs:
        takes = [p for p, r in body if not r]
        if (idle and "idle" in takes) or (not idle and set(takes) & goals):
            st = {p for p in head if p in tracked} | ({p for p, r in body if r and p in goals} if idle else set())
            if st:
                start.append(frozenset(st))
    seen, todo = set(), list(start)
    while todo:
        st = todo.pop()
        if st in seen:
            continue
        seen.add(st)
        for _, body, head in rs:
            takes = {p for p, r in body if not r and p in tracked}
            needs = {p for p, r in body if p in tracked} - goals
            if not takes or not needs <= st or "idle" in [p for p, r in body if not r]:
                continue
            if "idle" in head or set(head) & set(ends):   # it gives back idle, or ends: the work ends
                continue
            nxt = (st - takes) | {p for p in head if p in tracked}
            if nxt and nxt != st:
                todo.append(frozenset(nxt))
    return sorted(tuple(sorted(s)) for s in seen if not any(o < s for o in seen))


def cancel_rules(text, member, goal_kinds, ends=(), decls=""):
    """MEMBER's cancel rules over TEXT (its base; DECLS: the family package it includes, for the goal kinds'
    arities): one per state, and cancel_none for a member with idle."""
    ar = dict(arities(decls), **arities(text))
    idle = "idle" in private(text, member)
    out = []
    sts = states(text, member, goal_kinds, ends, crossing=arities(decls))
    if not sts:
        raise StubError("%s: its goal kinds %s reach no state (no rule takes the goal)" % (member, ", ".join(goal_kinds)))
    unknown = sorted({p for st in sts for p in st if p not in ar and p != "busy"})
    if unknown:
        raise StubError("%s: no declaration for %s (the base or the family package)" % (member, ", ".join(unknown)))
    for st in sts:
        toks, n = [], 0
        for p in st:
            k = ar.get(p, 0)
            toks.append("%s(%s)" % (p, ", ".join("V%d" % (n + i) for i in range(k))) if k else p)
            n += k
        name = "cancel_" + "_".join(p for p in st if p != "busy") if len(st) > 1 or not idle else "cancel"
        out += ["  %% Stopped: I drop my goal.",
                "  %s [dyn] : tick__cancel(%s) * %s -o %s." % (name, member, " * ".join(toks), "idle" if idle else "one")]
    if idle:
        out += ["  %% Stopped as I finished: nothing left to drop.",
                "  cancel_none [dyn] : idle * tick__cancel(%s) -o idle.   "
                "%% the race: its done and the stop in one director beat (path_pop, stop_cancel: the sampled order)" % member]
    return out

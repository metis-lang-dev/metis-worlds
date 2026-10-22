"""perceive.py — ScienceWorld's TEXT as atoms (world-scienceworld step 1). The agent's perception is
the room description (`look`), the inventory and the step's result line: never the object tree,
which carries the hidden properties (the oracle, tests only).

  here(R)                 the room the agent is in
  door(R2, open|closed)   a door from here to R2
  in(O, C)                O is in (or on) C: a room's things in the room, "On the table is: a, b",
                          "(containing a, b)", "In the sink is: …", "In the cupboard is: …"
  state(O, on|off)        "which is turned on/off", "which is on/off", "activated/deactivated"
  closed(C) / open(C)     "The cupboard door is closed." — a container with a door
  reads(O, nN)            a thermometer's reading (degrees, rounded, clamped to n-50..n300)
  holds(O)                the inventory
  said(KIND)              the result line, typed (the events: one beat)
Names: lower case, spaces → `_`, articles dropped ("a red light bulb" → red_light_bulb; "a substance
called air" → air)."""
import re

ARTICLE = re.compile(r"^(?:a|an|the|A|An|The)\s+")
MESSAGES = [
    (r"^you move to the (.+)\.", "moved"), (r"^the door is already open", "already_open"),
    (r"^the (.+) is now open\.", "opened"), (r"^the (.+) is now closed\.", "closed_it"),
    (r"you move the (.+) to the inventory", "picked"), (r"^you move the (.+) to the (.+)\.", "moved_obj"),
    (r"^you focus on the (.+)\.", "focused"), (r"is now connected to", "connected"), (r"is now disconnected", "disconnected"),
    (r"^you decide to wait", "waited"), (r"^this room is called", "looked"), (r"ambiguous request", "ambiguous"),
    (r"no known action matches|unknown action", "unknown"), (r"too far away|can't|cannot|is not open|isn't open|not able|nothing to", "cant"),
    (r"is now activated|turns on|now on", "activated"), (r"is now deactivated|turns off|now off", "deactivated"),
    (r"already|is not a|not possible|doesn't|does not", "cant"),
]


def label(s):
    """The world's own spelling of a thing (the referent a command must use: "unknown substance B")."""
    s = s.strip().strip(".,")
    s = ARTICLE.sub("", s)
    s = re.sub(r"^substance called ", "", s)
    s = re.sub(r",? which is .*$", "", s)
    s = re.sub(r",? currently reading .*$", "", s)
    s = re.sub(r"\s*\(containing .*\)$", "", s)
    return s.strip()


def name(s):
    s = s.strip().strip(".,")
    s = ARTICLE.sub("", s)
    s = re.sub(r"^substance called ", "", s)
    s = re.sub(r",? which is .*$", "", s)
    s = re.sub(r",? currently reading .*$", "", s)
    s = re.sub(r"\s*\(containing .*\)$", "", s)
    s = re.sub(r"\s+", "_", s.strip().lower())
    return s or "thing"


def _items(s):
    """'a bowl (containing a red apple, a banana), a drawer' → the top-level comma list."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur); cur = ""
        else:
            cur += ch
    out.append(cur)
    items = []
    for x in out:                                   # "a green light bulb, which is off": the clause stays with its item
        x = x.strip()
        if not x or x == "nothing":
            continue
        if x.startswith("which is") and items:
            items[-1] += ", " + x
        else:
            items.append(x)
    return items


LABELS = {}


def _item_atoms(text, container, atoms, names):
    """One item phrase inside CONTAINER: its name, its state, its own contents."""
    n = name(text)
    if n in ("agent",):
        return
    names.add(n)
    LABELS[n] = label(text)
    atoms.add("in(%s,%s)" % (n, container))
    m = re.search(r"which is (?:turned )?(on|off|activated|deactivated)", text)
    if m:
        atoms.add("state(%s,%s)" % (n, "on" if m.group(1) in ("on", "activated") else "off"))
    m = re.search(r"currently reading a temperature of (-?\d+)", text)
    if m:
        t = max(-50, min(300, int(m.group(1))))
        atoms.add("reads(%s,n%s)" % (n, str(t).replace("-", "m")))
    m = re.search(r"\(containing (.+)\)$", text.strip())
    if m:
        for it in _items(m.group(1)):
            _item_atoms(it, n, atoms, names)


def perceive_look(look, atoms, names):
    """The room description, line by line."""
    here = None
    m = re.search(r"This room is called the (.+?)\.", look)
    if m:
        here = name(m.group(1))
        atoms.add("here(%s)" % here)
    section = "in"
    for raw in look.split("\n")[1:]:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("You also see"):
            section = "doors"; continue
        if section == "doors":
            m = re.match(r"A door to the (.+?) \(that is (open|closed)\)", line)
            if m:
                atoms.add("door(%s,%s)" % (name(m.group(1)), m.group(2)))
            continue
        # "a table. On the table is: a, b." / "a sink, which is turned off. In the sink is: nothing." / "a cupboard. The cupboard door is closed."
        head, _, rest = line.partition(". ")
        _item_atoms(head, here or "room", atoms, names)
        n = name(head)
        m = re.search(r"(?:On|In) the .+? is: (.*?)\.?$", rest)
        if m:
            for it in _items(m.group(1)):
                _item_atoms(it, n, atoms, names)
        m = re.search(r"The .+? door is (open|closed)", rest)
        if m:
            atoms.add("%s(%s)" % (m.group(1), n))


def perceive_inv(inv, atoms, names):
    for raw in inv.split("\n")[1:]:
        line = raw.strip()
        if line and line != "nothing":
            n = name(line); names.add(n); LABELS[n] = label(line); atoms.add("holds(%s)" % n)
            m = re.search(r"\(containing (.+)\)$", line)
            if m:
                for it in _items(m.group(1)):
                    _item_atoms(it, n, atoms, names)


def events_of(text):
    t = (text or "").strip().lower()
    kinds = []
    for pat, kind in MESSAGES:
        if re.search(pat, t):
            kinds.append(kind)
            break
    return kinds or (["other"] if t else [])


def perceive(look, inv, result=""):
    atoms, names = set(), set()
    perceive_look(look or "", atoms, names)
    perceive_inv(inv or "", atoms, names)
    return {"atoms": sorted(atoms), "events": ["said(%s)" % k for k in events_of(result)], "message": result or "",
            "names": sorted(names), "labels": {n: LABELS[n] for n in names if n in LABELS and LABELS[n].lower().replace(" ", "_") != n}}


TASKS = [
    (r"determine if (?:the )?(.+?) is electrically conductive.*?conductive, place it in the (.+?) box\. If it is electrically nonconductive, place it in the (.+?) box",
     lambda m: "task(conductivity,%s,%s,%s)" % (name(m.group(1)), name(m.group(2)) + "_box", name(m.group(3)) + "_box")),
]


def task_atoms(desc):
    d = (desc or "").replace("\n", " ")
    for pat, mk in TASKS:
        m = re.search(pat, d)
        if m:
            return [mk(m)]
    return []

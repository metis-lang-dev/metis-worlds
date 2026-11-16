"""road_narrate.py — the road page's own narration and catalog watch (metis-plugin s-df4ff191 step 4: the pi LOOP dock is gone, so
the page's narrate no longer goes to the loop's /narrate; Claude Code works the catalog, the page notices when it changed).

    narrate(root, run, k0, k1)   -> {"members": {member: [lines]}, "text"}   the window of the page's own trace told in each
        member's rules' own %% words, bound to the firing (deterministic, 0 USD), the protocol's wordless rules and the director left out,
        the same words again at once said once (xN); the trace: <root>/.metis/traces/<run> (road_hier.traces_dir's)
    catalog_files(root, family) / snapshot(files) / changed(a, b)   the catalog's files by content: the road's domains and the family
        the members include (METIS_HOME), never .metis/, a build dir, the cases or the generated intent files (no behaviour);
        a change is what the page offers to reload

metispy only (metis.trace.timeline, metis.catalog, metis.domain.package.rule_docs): the same reading as the loop's narration, without the
loop."""
import hashlib
import os
import re
from pathlib import Path

SKIP = ("director",)


def _docs(root, member):
    try:
        from metis import catalog
        from metis.domain.package import rule_docs
        return rule_docs(catalog.get(member, str(root)).program)
    except Exception:                                   # a member the catalog cannot give: its rules are named, not said
        return {}


def _members(tdir):
    import json
    for f in sorted(Path(tdir).glob("seg-*.jsonl")):
        with open(f) as fh:
            head = json.loads(fh.readline())
        return list((head.get("members") or {}).keys())
    return []


def narrate(root, run, k0, k1):
    from metis import trace as T
    root = Path(root)
    if not re.match(r"^[\w.@#:+=-]+$", str(run)) or run in (".", ".."):
        raise ValueError("%r: not a run name" % (run,))
    tdir = root / ".metis" / "traces" / run
    if not tdir.is_dir():
        raise ValueError("no trace %s in %s" % (run, root / ".metis" / "traces"))
    k0, k1 = int(k0), int(k1)
    told = {}
    for m in _members(tdir):
        if any(s in m for s in SKIP):
            continue
        docs = _docs(root, m)
        ticks, _ = T.timeline(str(tdir), m)
        lines, last = [], None
        for t in ticks:
            if t.k < k0 or t.k > k1:
                continue
            for name in t.fired:
                base, _, bind = name.partition("[")
                doc = docs.get(base)
                if not doc:                             # the protocol's own rules (decide, back): no words for a tester
                    continue
                vals = dict(x.split("=", 1) for x in bind.rstrip("]").split(",") if "=" in x)
                said = re.sub(r"\{(\w+)\}", lambda g: vals.get(g.group(1), g.group(0)), doc).replace("_", " ")
                if last and last[0] == said:
                    last[1] += 1
                    lines[-1] = "%s (x%d)" % (said, last[1])
                    continue
                lines.append(said)
                last = [said, 1]
        if lines:
            told[m] = lines
    if not told:
        text = "Nothing my rules have words for fired in %d..%d: I drove on as before." % (k0, k1)
    else:
        text = " ".join("%s: %s" % ("The " + m, "; ".join(ls)) for m, ls in told.items())
    return {"members": told, "text": text}


def catalog_files(root, family=None):
    out = []
    bases = [Path(root) / "domains"] + ([Path(family)] if family else [])
    for base in bases:
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.suffix in (".llp", ".yaml", ".yml") and not any(
                    part in ("build", ".metis", "__pycache__", "records", "goldens", "cases", "eval", "intent")
                    for part in p.relative_to(base).parts):
                out.append(p)
    return out


def snapshot(files):
    snap = {}
    for p in files:
        try:
            snap[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        except OSError:
            continue
    return snap


def changed(a, b):
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def rel(paths, root, family=None):
    """Each path relative to its most specific base: the family's as family:PATH, the workspace's as PATH."""
    bases = sorted([(Path(family).resolve(), "family:")] if family else [], key=lambda b: -len(str(b[0])))
    bases += [(Path(root).resolve(), "")]
    bases.sort(key=lambda b: -len(str(b[0])))
    out = []
    for p in paths:
        rp = Path(p).resolve()
        for base, tag in bases:
            if rp == base or base in rp.parents:
                out.append(tag + os.path.relpath(rp, base))
                break
        else:
            out.append(str(p))
    return out

"""iface_gen.py — a family's INTERFACE PACKAGE generated from the interface check's cut (specialist-tree s-404d001f
step 3b, the architect's rule: the iface move is mechanical, the check the oracle; the learning loop's domains get
the same tool). No world's names in here: the cut and the members' own declarations say everything.

    python3 tools/iface_gen.py COMPOSITION.yaml FAMILY [--bases DIR] [--out DIR] [--write] [--metisc PATH]
    (COMPOSITION: an installed one, whose cut the check gives; --bases: the directory of the bases to rewrite — the
    repo's domains/hier for a committed world; default the composition's; --out: where iface/FAMILY.llp goes,
    default --bases: minihack, whose bases are generated, writes its package into the repo and strips at install)

1. `metisc --interface COMPOSITION.yaml` (METIS_CATALOG / METIS_HOME as the composition needs) → its `cut` block:
   every pred that crosses between the members, the director, the world — with its nature and its producers and
   consumers. The first run, when the composition's `interfaces:` names the package not written yet, checks a
   copy of the composition without it.
2. The family's vocabulary: the cut's preds but the protocol's (tick__*) and the resources. None (the members share
   only the protocol and resources: an empty cut): no package; the tool says so and writes nothing.
3. Each pred's signature from the members' declarations (`pred NAME(T1, …) : ns.` in their bases, or in the
   family package when it exists already). Several signatures: REFUSED with the list — the one manual step is
   the rename the check demands (refused_take / refused_put …). A pred in the package that no longer crosses:
   REFUSED while a member still uses it undeclared (declare it there by hand, then rerun).
4. --write: iface/FAMILY.llp (declaration only, preds sorted) and iface/FAMILY.yaml (natures: every family pred a
   signal, spec/15 §10.1 — but the natures the family's iface/FAMILY.yaml already names are kept: the per-pred table
   the tool reads, so a pred set to report, as gave_up, stays one across regenerations) under --out; each member base's crossing declarations stripped, an
   `include "iface/FAMILY.llp".` after its `types (…)` line. Idempotent: on a moved world it writes the same
   bytes and strips nothing.

As a library: cut(...), vocabulary(...), signatures(...), iface_text(...), natures_text(...), strip(text, preds,
family) — mh_hier applies strip() to its generated bases at install."""
import os
import re
import subprocess
import sys
from pathlib import Path

PRED = re.compile(r"^pred (\w+)(?:\(([^)]*)\))?\s*:\s*(\w+)\s*\.")


def bootstrap(comp):
    """COMP, or a copy beside it whose `interfaces:` leaves out the packages not written yet (the first run: the
    family package is what this tool makes) → (path, temporary?)."""
    text = comp.read_text()
    m = re.search(r"^interfaces: \[([^\]]*)\]\n", text, re.M)
    if not m:
        return comp, False
    have = [i.strip() for i in m.group(1).split(",") if i.strip() and (comp.parent / i.strip()).exists()]
    if len(have) == len([i for i in m.group(1).split(",") if i.strip()]):
        return comp, False
    tmp = comp.with_name(".iface_gen." + comp.name)
    tmp.write_text(text.replace(m.group(0), "interfaces: [%s]\n" % ", ".join(have) if have else ""))
    return tmp, True


def cut(composition, metisc="metisc", env=None):
    """{pred: {"nature": str, "out": [member…], "in": [member…], "resource": bool}} from the check's cut block."""
    comp, tmp = bootstrap(Path(composition).resolve())
    try:
        p = subprocess.run([metisc, "--interface", str(comp)], capture_output=True, text=True, env=env, cwd=str(comp.parent))
    finally:
        if tmp:
            comp.unlink()
    out, on = {}, False
    for line in p.stdout.splitlines():
        if line.startswith("cut "):
            on = True
            continue
        if on and not line.startswith("  "):
            break
        if on:
            m = re.match(r"^\s+(\w+) (\w+): out \[([^\]]*)\] in \[([^\]]*)\](?: resource \[([^\]]*)\])?", line)
            if m:
                out[m.group(1)] = {"nature": m.group(2), "out": m.group(3).split(), "in": m.group(4).split(),
                                   "resource": m.group(2) == "resource"}
    broken = [l for l in p.stdout.splitlines() if l.startswith("error compile ")]
    if broken or not out:                                       # a member that does not compile is missing from the cut
        raise RuntimeError("metisc --interface %s gave no whole cut:\n%s" % (comp, "\n".join(broken) or (p.stdout + p.stderr)[-2000:]))
    return out


def vocabulary(c):
    """The family's crossing preds: the cut's, but the protocol's and the resources."""
    return sorted(p for p, e in c.items() if not p.startswith("tick__") and not e["resource"])


def declarations(text):
    """{pred: (arg types)} declared in TEXT."""
    out = {}
    for line in text.splitlines():
        m = PRED.match(line.strip())
        if m:
            out[m.group(1)] = tuple(a.strip() for a in (m.group(2) or "").split(",") if a.strip())
    return out


def signatures(preds, texts):
    """{pred: {signature: [who…]}} over TEXTS {who: text} for PREDS."""
    out = {p: {} for p in preds}
    for who, t in sorted(texts.items()):
        for p, sig in declarations(t).items():
            if p in out:
                out[p].setdefault(sig, []).append(who)
    return out


def check_signatures(sigs):
    """The preds with no signature or several: the manual renames the check demands. → [message…]."""
    bad = []
    for p, by in sorted(sigs.items()):
        if len(by) > 1:
            bad.append("%s has several signatures: %s — rename one per signature" % (
                p, "; ".join("%s(%s) in %s" % (p, ", ".join(s), " ".join(w)) for s, w in sorted(by.items()))))
        elif not by:
            bad.append("%s crosses but no member declares it" % p)
    return bad


def iface_text(family, sigs, types):
    lines = ["%% %s — the %s family's interface package: the preds that cross between its members (generated by" % (family, family),
             "% metis-worlds tools/iface_gen.py from the interface check's cut; regenerate, never edit). Declaration only.",
             "catalog %s_iface 1." % family, 'provenance text "the %s family\'s crossing preds, from the interface check\'s cut" "2026-10-25".' % family,
             "types (%s)." % " ".join(types), "", "namespace %s_iface produce (dyn)." % family, ""]
    for p, by in sorted(sigs.items()):
        (sig,) = by
        lines.append("pred %s%s : %s_iface." % (p, "(%s)" % ", ".join(sig) if sig else "", family))
    return "\n".join(lines) + "\n"


NATURES = ("signal", "resource", "report")


def natures_of(path):
    """The per-pred natures an iface/FAMILY.yaml names ({} when there is none): the table a regeneration keeps."""
    import yaml
    p = Path(path)
    t = (yaml.safe_load(p.read_text()) or {}).get("nature") or {} if p.exists() else {}
    bad = {k: v for k, v in t.items() if v not in NATURES}
    if bad:
        raise ValueError("%s: natures %s are none of %s" % (path, bad, "/".join(NATURES)))
    return t


def natures_text(family, preds, table=None):
    """FAMILY's natures: each pred's from TABLE (the family's yaml as it was: a hand-set report or resource stays one),
    a signal for a pred the table does not name (spec/15 §10.1)."""
    table = table or {}
    return ("# %s — the natures of the family's crossing preds (spec/15 I11; generated by tools/iface_gen.py, the natures\n"
            "# this file names kept, a new pred a signal)\n"
            "nature: {%s}\n" % (family, ", ".join("%s: %s" % (p, table.get(p, "signal")) for p in sorted(preds))))


def strip(text, preds, family):
    """TEXT with its declarations of PREDS removed and `include "iface/FAMILY.llp".` after its `types (…)` line
    (once). Idempotent."""
    inc = 'include "iface/%s.llp".' % family
    out, have = [], inc in text
    for line in text.split("\n"):
        m = PRED.match(line.strip())
        if m and m.group(1) in preds:
            continue
        out.append(line)
        if not have and line.startswith("types ("):
            out.append(inc + "   % the family's crossing preds, declared once (tools/iface_gen.py)")
            have = True
    return "\n".join(out)


def types_of(sigs):
    return sorted({t for by in sigs.values() for sig in by for t in sig})


def generate(composition, family, bases, out_dir=None, metisc="metisc", env=None, write=False):
    """The cut (of the installed COMPOSITION) → the family package and the stripped bases. BASES: {member: base
    file} (the sources to rewrite: the repo's, or the install's); OUT_DIR: where iface/FAMILY.llp goes (default
    beside the composition). → (iface text, natures, {member: new base text}, problems); an empty cut → (None,
    None, the bases unchanged, []): no package to write."""
    c = cut(composition, metisc, env)
    preds = vocabulary(c)
    hier = Path(out_dir).resolve() if out_dir else Path(composition).resolve().parent
    texts = {m: Path(b).read_text() for m, b in bases.items()}
    fam = hier / "iface" / ("%s.llp" % family)
    if not preds:
        return None, None, texts, []
    if fam.exists():
        texts["iface"] = fam.read_text()
    sigs = signatures(preds, texts)
    gone = set(declarations(texts.get("iface", ""))) - set(preds)        # out of the cut, maybe still used by one member
    problems = check_signatures(sigs) + ["%s no longer crosses but %s uses it — declare it there" % (p, m) for p in sorted(gone)
                                         for m in sorted(bases) if re.search(r"\b%s\b" % p, texts[m]) and p not in declarations(texts[m])]
    if problems:
        return None, None, None, problems
    it, nt = iface_text(family, sigs, types_of(sigs)), natures_text(family, preds, natures_of(fam.with_suffix(".yaml")))
    new = {m: strip(texts[m], set(preds), family) for m in bases}
    if write:
        fam.parent.mkdir(parents=True, exist_ok=True)
        fam.write_text(it)
        fam.with_suffix(".yaml").write_text(nt)
        for m, b in bases.items():
            if new[m] != texts[m]:
                Path(b).write_text(new[m])
    return it, nt, new, []


if __name__ == "__main__":
    comp, family = sys.argv[1], sys.argv[2]
    metisc = sys.argv[sys.argv.index("--metisc") + 1] if "--metisc" in sys.argv else os.environ.get("METISC", "metisc")
    src = Path(sys.argv[sys.argv.index("--bases") + 1]) if "--bases" in sys.argv else Path(comp).resolve().parent
    import yaml
    members = yaml.safe_load(Path(comp).read_text())["specialists"]
    bases = {m: str(src / ("%s_domain.llp" % m)) for m in members}
    before = {m: Path(b).read_text() for m, b in bases.items()}
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else src
    it, nt, new, problems = generate(comp, family, bases, out, metisc, write="--write" in sys.argv)
    if problems:
        print("\n".join("REFUSED " + p for p in problems))
        sys.exit(1)
    if it is None:
        fam = out / "iface" / ("%s.llp" % family)
        print("empty cut, no package: the members share only the protocol (tick__*) and resources" +
              ("; %s exists from before — remove it and its includes by hand" % fam if fam.exists() else ""))
        sys.exit(0)
    print(it, end="")
    print("stripped:", ", ".join(m for m in bases if new[m] != before[m]) or "none")

"""ports — the contract between the library and a rule program over roles, one for every world. Plain strings in,
strings and numbers out; no program syntax beyond `pred(args)`.

- translate(reading, binding): the world's facts (atom → count, the world's names) over the bound entries only,
  said in roles — a fact naming anything unbound is not read;
- sync_diff(reading, counts, owned): the do-lines that bring a live session's facts to the reading (`+atom n`,
  `-atom n`), retracting only the predicates the host owns (the program's own tokens untouched);
- in_room(atom, handle): an atom of roles with its roles as the world's names (the wire, the page, the voice);
- say_in_roles(atom, inverse): an atom of the world's names said in roles (an intent the person typed);
- names(binding, keep): name(role, thing) as data;
- readings are the adapter's (a weight port's value from the belief: bayes.normalized)."""


def args(atom):
    return [s.strip() for s in atom[atom.index("(") + 1:-1].split(",")] if "(" in atom else []


def translate(reading, binding):
    """READING's facts whose every argument is bound, in roles (BINDING: {role: name}). → {atom: n}."""
    inv = {h: r for r, h in binding.items()}
    out = {}
    for a, n in reading.items():
        name = a.split("(")[0]
        xs = args(a) if "(" in a else []
        if all(x in inv for x in xs):
            out["%s(%s)" % (name, ",".join(inv[x] for x in xs)) if xs else name] = n
    return out


def sync_diff(reading, counts, owned):
    """The do-lines from COUNTS (the session's) to READING: asserted what the reading holds more of, retracted what
    it no longer holds — of the predicates in OWNED only (the world's; the program's own tokens stay)."""
    dos = []
    for a, n in sorted(reading.items()):
        have = counts.get(a, 0)
        if n > have:
            dos.append("+%s %d" % (a, n - have))
    for a, have in sorted(counts.items()):
        if have > 0 and a not in reading and a.split("(")[0] in owned:
            dos.append("-%s %d" % (a, have))
    return dos


def in_room(atom, handle):
    """ATOM's arguments as HANDLE(role) names them (a constant that is no role, or an unbound role, stays)."""
    if "(" not in atom:
        return atom
    name, _, rest = atom.partition("(")
    return "%s(%s)" % (name, ",".join(handle(a.strip()) or a.strip() for a in rest.rstrip(")").split(",")))


def say_in_roles(name, xs, inverse):
    """name(xs) with each world name its role (INVERSE: {name: role}); a name with no role stays."""
    return "%s(%s)" % (name, ",".join(inverse.get(a, a) for a in xs)) if xs else name


def names(binding, keep):
    """name(role, thing) for the roles in KEEP: [[role, name], …] sorted."""
    return sorted([r, h] for r, h in binding.items() if r in keep)

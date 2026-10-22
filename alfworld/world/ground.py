"""ground.py — ALFWorld's PDDL facts as the program's atoms (world-alfworld step 1).

The game names its things with coordinates (`spoon_bar__plus_01_dot_23_bar__…`); the
program needs identifiers. A Handles table gives every game object a short name — its
class and a running number in order of first appearance (`spoon1`, `countertop2`,
`loc3`) — and keeps the map both ways for the host (a rule's argument back to the
game's name in a command) and the generator (the instance's types and facts).

Predicates: the agent is one, so its argument is dropped; names are lowercased and
shortened where the PDDL's are long. STATIC predicates (never change in a game) become
the instance's Horn facts; DYNAMIC ones its `#init` and the host's reading.
"""
import re

# the PDDL predicate (textworld lowercases them) -> (the atom's name, which arguments to keep)
PRED = {
    "atLocation": ("at", (1,)),                  # (agent, location) -> at(location)
    "receptacleAtLocation": ("recat", (0, 1)),
    "objectAtLocation": ("objat", (0, 1)),
    "openable": ("openable", (0,)),
    "opened": ("opened", (0,)),
    "inReceptacle": ("inrecep", (0, 1)),
    "isReceptacleObject": ("recobj", (0,)),
    "inReceptacleObject": ("inrecobj", (0, 1)),
    "isReceptacleObjectFull": ("recobjfull", (0,)),
    "wasInReceptacle": ("wasin", (0, 1)),
    "checked": ("checked", (0,)),
    "examined": ("examined", (0,)),
    "receptacleType": ("rtype", (0, 1)),
    "canContain": ("cancontain", (0, 1)),
    "objectType": ("otype", (0, 1)),
    "holds": ("holds", (1,)),                    # (agent, object) -> holds(object)
    "holdsAny": ("holding", ()),
    "holdsAnyReceptacleObject": ("holdingrecobj", ()),
    "full": ("full", (0,)),
    "isClean": ("clean", (0,)),
    "cleanable": ("cleanable", (0,)),
    "isHot": ("hot", (0,)),
    "heatable": ("heatable", (0,)),
    "isCool": ("cool", (0,)),
    "coolable": ("coolable", (0,)),
    "pickupable": ("pickupable", (0,)),
    "moveable": ("moveable", (0,)),
    "toggleable": ("toggleable", (0,)),
    "isOn": ("on", (0,)),
    "isToggled": ("toggled", (0,)),
    "sliceable": ("sliceable", (0,)),
    "isSliced": ("sliced", (0,)),
}
PRED = {k.lower(): v for k, v in PRED.items()}
STATIC = {"recat", "openable", "recobj", "rtype", "cancontain", "otype", "cleanable", "heatable", "coolable",
          "pickupable", "moveable", "toggleable", "sliceable"}
DYNAMIC = {a for a, _ in PRED.values()} - STATIC
# the complementary pairs the program keeps (LL has no negation): atom -> its complement
PAIRS = {"holding": "handsfree"}

_CLASS = re.compile(r"^([A-Za-z]+)")


def pddl_type_const(name):
    """`cabinettype` (textworld lowercases `CabinetType`) -> `cabinet_t`."""
    n = name.lower()
    return n[:-4] + "_t" if n.endswith("type") else n


class Handles:
    """Game names <-> the program's identifiers, per game."""

    def __init__(self):
        self.to_handle, self.to_name, self.counts, self.kind = {}, {}, {}, {}

    def handle(self, name, kind):
        if name in self.to_handle:
            return self.to_handle[name]
        if kind in ("otype", "rtype"):
            h = pddl_type_const(name)
        elif kind == "agent":
            h = "agent"
        elif kind == "location":
            n = self.counts["loc"] = self.counts.get("loc", 0) + 1
            h = "loc%d" % n
        else:
            cls = (_CLASS.match(name).group(1) if _CLASS.match(name) else "thing").lower()
            n = self.counts[cls] = self.counts.get(cls, 0) + 1
            h = "%s%d" % (cls, n)
        self.to_handle[name], self.to_name[h], self.kind[h] = h, name, kind
        return h

    def by_kind(self, kind):
        return sorted(h for h, k in self.kind.items() if k == kind)

    def as_json(self):
        return {"to_name": self.to_name, "kind": self.kind}

    @classmethod
    def from_json(cls, d):
        """The generator's map, reused by the host so the program's names are the game's."""
        h = cls()
        for handle, name in d["to_name"].items():
            h.to_handle[name], h.to_name[handle], h.kind[handle] = handle, name, d["kind"][handle]
            m = re.match(r"^([a-z_]+?)(\d+)$", handle)
            if m:
                h.counts[m.group(1)] = max(h.counts.get(m.group(1), 0), int(m.group(2)))
        return h


def atom_of(prop, handles):
    """A textworld Proposition -> (atom, static?) or None when the predicate is not modelled."""
    spec = PRED.get(prop.name.lower())
    if spec is None:
        return None
    name, keep = spec
    args = []
    for i in keep:
        a = prop.arguments[i]
        args.append(handles.handle(a.name, a.type))
    atom = name + ("(" + ",".join(args) + ")" if args else "")
    return atom, name in STATIC


def atoms_of(facts, handles):
    """Every modelled fact -> {atom}, split static / dynamic (sorted)."""
    static, dynamic = set(), set()
    for p in sorted(facts, key=str):            # a set: ordered, so handles are numbered the same every run
        r = atom_of(p, handles)
        if r is None:
            continue
        atom, is_static = r
        (static if is_static else dynamic).add(atom)
    return sorted(static), sorted(dynamic)

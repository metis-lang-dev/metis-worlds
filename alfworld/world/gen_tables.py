"""gen_tables.py — ALFRED's room statistics the semantic map's search reads, from every ALFWorld game (map-queries
s-396939dc step 1; alf-tasks steps 2-3). One pass over $ALFWORLD_DATA/json_2.1.1/*/*/trial_*/game.tw-pddl, three tables
under world/:

    cancontain.json   {object type: [receptacle types]}: the union of canContain over the games (ALFRED's
                      compatibility, no room's): where a kind COULD be
    presence.json     {room type: {object type: fraction of that type's scenes whose objects include it}}, and the
                      scenes per type: whether a kind is in a room at all (the existence belief's prior)
    starts.json       {object type: {receptacle type: games whose initial state starts it in or on that type}}, and
                      the receptacles of each type over the scenes: where a kind usually IS (the place prior)

    ALFWORLD_DATA=… python3 world/gen_tables.py [--check]

--check exits 1 when a table is not as written here. The room types are ALFRED's floor-plan ranges. An object's name
in a game carries its position, which varies per trial, so the starts count games, not instances; a receptacle's
name is fixed per scene, so the receptacles are counted once per scene."""
import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOMS = ((1, 30, "kitchen"), (201, 230, "living room"), (301, 330, "bedroom"), (401, 430, "bathroom"))


def room_of(scene):
    return next((r for a, b, r in ROOMS if a <= scene <= b), None)


def tables(root):
    comp = collections.defaultdict(set)
    scenes = collections.defaultdict(set)
    starts = collections.defaultdict(collections.Counter)
    receptacles, seen_r = collections.Counter(), set()
    for f in sorted(glob.glob(os.path.join(root, "*", "*", "trial_*", "game.tw-pddl"))):
        scene = int(f.split(os.sep)[-3].rsplit("-", 1)[1])
        p = json.load(open(f))["pddl_problem"]
        init = p[p.find("(:init"):p.find("(:goal")]
        for rt, ot in re.findall(r"\(canContain (\w+)Type (\w+)Type\)", p):
            comp[ot.lower() + "_t"].add(rt.lower() + "_t")
        ot = dict(re.findall(r"\(objectType (\S+) (\w+)Type\)", init))
        rt = dict(re.findall(r"\(receptacleType (\S+) (\w+)Type\)", init))
        scenes[scene] |= {t.lower() + "_t" for t in ot.values()}
        for r, t in rt.items():
            if (scene, r) not in seen_r:
                seen_r.add((scene, r))
                receptacles[t.lower() + "_t"] += 1
        for o, r in re.findall(r"\(inReceptacle (\S+) (\S+)\)", init):
            if o in ot and r in rt:
                starts[ot[o].lower() + "_t"][rt[r].lower() + "_t"] += 1
    by_room = collections.defaultdict(list)
    for n, kinds in scenes.items():
        if room_of(n):
            by_room[room_of(n)].append(kinds)
    src = "every ALFWorld game (json_2.1.1, all splits): world/gen_tables.py"
    return {
        "cancontain.json": {"source": "the union of canContain over " + src + ": ALFRED's receptacle compatibility, no room's",
                            "cancontain": {o: sorted(v) for o, v in sorted(comp.items())}},
        "presence.json": {"source": "the fraction of ALFRED's scenes of each room type whose objects include the kind, " + src,
                          "scenes": {r: len(ss) for r, ss in sorted(by_room.items())},
                          "presence": {r: {k: round(sum(k in s for s in ss) / len(ss), 3) for k in sorted(set().union(*ss))}
                                       for r, ss in sorted(by_room.items())}},
        "starts.json": {"source": "per object type, the games whose initial state starts it in or on each receptacle type, and the "
                                  "receptacles of each type over the scenes (one per scene), " + src,
                        "starts": {o: dict(sorted(c.items(), key=lambda x: (-x[1], x[0]))) for o, c in sorted(starts.items())},
                        "receptacles": dict(sorted(receptacles.items()))},
    }


def main(argv):
    data = os.environ.get("ALFWORLD_DATA")
    if not data:
        raise SystemExit("gen_tables: ALFWORLD_DATA is not set")
    out, stale = tables(os.path.join(data, "json_2.1.1")), []
    for name, t in out.items():
        path = os.path.join(HERE, name)
        text = json.dumps(t, indent=1) + "\n"
        if "--check" in argv:
            if not os.path.exists(path) or open(path).read() != text:
                stale.append(name)
        else:
            open(path, "w").write(text)
    if stale:
        print("gen_tables: not as written here (run without --check): %s" % ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""gen_room_tree.py — the room tree metis-worlds CI checks (map-queries s-396939dc step 3): kitchen 13 installed as a room
(gen_hier.install, a tick tree with the person), its sources only — the composition, every member's program and
domain.yaml, the family interface, the task's intent card and world model — under tests/room_tree/. CI has no game
data; it builds metisc from metis-lang master and runs `metisc --interface domains/hier/composition.yaml` there, so a
type-name clash with the director's routing type (alf-tasks step 2's `kind`: I6, two member sets of one type) fails
CI, not the person's session.

    ALFWORLD_DATA=… python3 world/gen_room_tree.py [--check]

--check exits 1 when the snapshot is not what the generator installs now (a test on the dev machine runs it)."""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "tests", "room_tree")
ROOM = "kitchen 13"


def sources(root):
    """{relative path: text} of the install's sources: .llp and .yaml, not the members' cases (metispy's stub runs
    those), the flat package, the hosts, the game data or the run's logs."""
    out = {}
    for d, _, files in os.walk(os.path.join(root, "domains")):
        rel = os.path.relpath(d, root)
        if "_flat" in rel.split(os.sep) or "cases" in rel.split(os.sep):
            continue
        for f in files:
            if f.endswith((".llp", ".yaml")):
                out[os.path.join(rel, f)] = open(os.path.join(d, f)).read()
    return out


def main(argv):
    if not os.environ.get("ALFWORLD_DATA"):
        raise SystemExit("gen_room_tree: ALFWORLD_DATA is not set")
    sys.path[:0] = [HERE, os.path.join(os.path.dirname(HERE), "experiments")]
    import demo
    import gen_hier
    tmp = tempfile.mkdtemp(prefix="room_tree.")
    try:
        gen_hier.install(str(demo.resolve(ROOM)), os.path.join(tmp, "root"), person=True, tree=True, room=True)
        new = sources(os.path.join(tmp, "root"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if "--check" in argv:
        old = sources(OUT) if os.path.isdir(OUT) else {}
        stale = sorted(p for p in set(old) | set(new) if old.get(p) != new.get(p))
        if stale:
            print("gen_room_tree: not as written here (run without --check): %s" % ", ".join(stale), file=sys.stderr)
            return 1
        return 0
    shutil.rmtree(OUT, ignore_errors=True)
    for p, text in sorted(new.items()):
        os.makedirs(os.path.dirname(os.path.join(OUT, p)), exist_ok=True)
        with open(os.path.join(OUT, p), "w") as f:
            f.write(text)
    print("gen_room_tree: %d files under %s" % (len(new), os.path.relpath(OUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

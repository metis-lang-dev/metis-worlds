"""The world under test (world-minihack step 1): the perception, the host, the level
families, the generated package. Runs under the world's venv; the program check needs METISC."""
import os, subprocess, sys
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "world"))
from mh_gym import World  # noqa: E402
from mh_host import MhHost, bindings, ACTIONS  # noqa: E402
import levels  # noqa: E402
import gen_level  # noqa: E402

VARIANT = ("medium", "apple", "newt", "closed", "none")


def test_level_families_and_splits():
    d, h = levels.split("room", "discovery"), levels.split("room", "held_out")
    assert len(d) + len(h) == len(levels.all_variants()) == 144
    assert all(levels.is_held_out(v) for v in h) and not any(levels.is_held_out(v) for v in d)
    assert ("small", "apple", "newt", "none", "pit") in h and ("small", "key", "none", "closed", "none") in h


def test_perception_of_a_level():
    lv = levels.level(VARIANT, seed=1)
    w = World()
    info = w.open(des=lv["des"], actions=ACTIONS, max_steps=20, seed=1)
    atoms = set(info["init"]["atoms"])
    assert info["size"] == [7, 5] and len(info["cells"]) == 35
    assert any(a.startswith("agent_at(") for a in atoms) and any(a.startswith("obj(apple,") for a in atoms)
    assert any(a.startswith("monster(newt,") for a in atoms) and any(a.startswith("door(") for a in atoms)
    assert any(a.startswith("stairs_down(") for a in atoms) and "hunger(normal)" in atoms
    s = w.step("WAIT")
    assert "atoms" in s and not s["done"]


def test_bindings():
    assert bindings("cmd_move_rule[D=n]") == ("cmd_move_rule", {"D": "n"})


@pytest.fixture
def package(tmp_path):
    pkg, n = gen_level.generate(VARIANT, 1, str(tmp_path))
    assert n > 20 and os.path.exists(os.path.join(pkg, "level.json")) and os.path.exists(os.path.join(pkg, "intent.yaml"))
    return pkg


def test_host_moves_picks_up_and_restores(package):
    h = MhHost(package)
    try:
        r = h.reading()
        at = next(a for a in r if a.startswith("agent_at("))[9:-1]
        apple = next(a for a in r if a.startswith("obj(apple,"))[10:-1]
        ax, ay = map(int, at[1:].split("_")); px, py = map(int, apple[1:].split("_"))
        for _ in range(20):
            if (ax, ay) == (px, py):
                break
            dx, dy = (px > ax) - (px < ax), (py > ay) - (py < ay)
            d = {(0, -1): "n", (0, 1): "s", (1, 0): "e", (-1, 0): "w", (1, -1): "ne", (-1, -1): "nw", (1, 1): "se", (-1, 1): "sw"}[(dx, dy)]
            assert h.tick({a: 1 for a in h.reading()}) is not None
            h.on_event("cmd_move[D=%s]" % d, ())
            at = next(a for a in h.reading() if a.startswith("agent_at("))[9:-1]
            ax, ay = map(int, at[1:].split("_"))
        assert (ax, ay) == (px, py), "the walk did not reach the apple"
        h.on_event("cmd_pickup", ())
        assert "holds(apple)" in h.reading() and not any(a.startswith("obj(apple,") for a in h.reading())
        assert any(k.startswith("said(") for k in h.pending_events)      # the message became an event
        snap = h.snapshot()
        h.restore(snap)
        assert "holds(apple)" in h.reading() and len(h.actions) == len(snap["actions"])
    finally:
        h.gym.close()


@pytest.mark.skipif(not os.environ.get("METISC"), reason="METISC is not set")
def test_package_compiles(package):
    llp = next(f for f in os.listdir(package) if f.endswith(".llp"))
    out = subprocess.run([os.environ["METISC"], "--diagnostics-json", os.path.join(package, llp)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and "error" not in out.stdout.lower(), out.stdout[-400:] + out.stderr[-200:]

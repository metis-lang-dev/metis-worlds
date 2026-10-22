"""The world under test (world-scienceworld step 1): the perceiver on fixed texts, the gym on a
variation, the gold path through the host, the restore, the package compiling. Runs under the
world's venv (.worlds/sw or scienceworld/.venv); the program check needs METISC."""
import os, subprocess, sys
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "world"))
sys.path.insert(0, os.path.join(ROOT, "experiments"))
import perceive  # noqa: E402
from sw_host import SwHost, bindings  # noqa: E402
import gen_instance  # noqa: E402

LOOK = """This room is called the kitchen. In it, you see: 
\tthe agent
\ta substance called air
\ta chair. On the chair is: nothing.
\ta counter. On the counter is: a bowl (containing a red apple, a banana, an orange, a potato), a drawer.
\ta cupboard. The cupboard door is closed. 
\ta oven, which is turned off. The oven door is closed. 
\ta sink, which is turned off. In the sink is: nothing.
\ta stopwatch, which is deactivated. 
\ta table. On the table is: a glass cup (containing nothing).
\ta thermometer, currently reading a temperature of 10 degrees celsius
\ta red light bulb, which is on
You also see:
\tA door to the bathroom (that is open)
\tA door to the hallway (that is closed)"""
INV = "In your inventory, you see:\n\tan orange"


def test_perceiver_reads_the_room():
    p = perceive.perceive(LOOK, INV, "You move to the kitchen.")
    a = set(p["atoms"])
    assert "here(kitchen)" in a and "door(bathroom,open)" in a and "door(hallway,closed)" in a
    assert "in(counter,kitchen)" in a and "in(bowl,counter)" in a and "in(red_apple,bowl)" in a and "in(drawer,counter)" in a
    assert "closed(cupboard)" in a and "state(oven,off)" in a and "closed(oven)" in a and "state(stopwatch,off)" in a
    assert "in(glass_cup,table)" in a and "reads(thermometer,n10)" in a and "state(red_light_bulb,on)" in a
    assert "holds(orange)" in a and "in(air,kitchen)" in a and not any(x.startswith("in(agent") for x in a)
    assert p["events"] == ["said(moved)"]
    assert perceive.events_of("The door is already open.") == ["already_open"]
    assert perceive.events_of("terminal 1 on aluminum foil is now connected to terminal 2 on black wire") == ["connected"]
    assert perceive.task_atoms("Your task is to determine if aluminum foil is electrically conductive. The aluminum foil is located around the workshop. First, focus on the aluminum foil. If it is electrically conductive, place it in the red box. If it is electrically nonconductive, place it in the green box.") == ["task(conductivity,aluminum_foil,red_box,green_box)"]


def test_bindings():
    assert bindings("cmd_connect[A=battery_anode,B=blue_wire_terminal_1]") == ("cmd_connect", {"A": "battery_anode", "B": "blue_wire_terminal_1"})


@pytest.fixture(scope="module")
def package(tmp_path_factory):
    pkg, n = gen_instance.generate("test-conductivity", 0, str(tmp_path_factory.mktemp("pkg")))
    assert n > 10 and os.path.exists(os.path.join(pkg, "task.json")) and os.path.exists(os.path.join(pkg, "intent.yaml"))
    return pkg


def test_gold_path_wins_through_the_host(package):
    from baseline import command_event
    h = SwHost(package)
    try:
        r = h.reading()
        assert "here(hallway)" in r and "task(conductivity,aluminum_foil,red_box,green_box)" in r
        gold = h.gym.call("gold")["gold"]
        assert len(gold) > 10
        for a in gold:
            h.on_event(command_event(a), ())
            if h.done:
                break
        assert h.won and h.score >= 100, (h.score, h.message)
        r = h.reading()
        assert "focused(aluminum_foil)" in r                      # kept from the result line (the look never says it)
        assert any(k.startswith("state(red_light_bulb,on)") for k in r) or h.done   # the experiment's answer was seen before the verdict
        assert any(k.startswith("said(") for k in h.pending_events)
    finally:
        h.gym.close()


def test_refusal_and_restore(package):
    h = SwHost(package)
    try:
        h.on_event("cmd_go[R=nowhere]", ())
        assert h.pending_events[-1] in ("said(unknown)", "said(cant)") and "here(hallway)" in h.reading()   # the world's own refusal, nothing moved
        h.on_event("cmd_go[R=workshop]", ())
        assert "here(workshop)" in h.reading()
        t1 = h.t
        snap = h.snapshot()
        h.on_event("cmd_take[O=aluminum_foil]", ())
        assert "holds(aluminum_foil)" in h.reading()
        h.restore(snap)
        assert "holds(aluminum_foil)" not in h.reading() and "here(workshop)" in h.reading() and h.t == t1
    finally:
        h.gym.close()


@pytest.mark.skipif(not os.environ.get("METISC"), reason="METISC is not set")
def test_package_compiles(package):
    llp = next(f for f in os.listdir(package) if f.endswith(".llp"))
    out = subprocess.run([os.environ["METISC"], "--diagnostics-json", os.path.join(package, llp)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and "error" not in out.stdout.lower(), out.stdout[-400:] + out.stderr[-200:]

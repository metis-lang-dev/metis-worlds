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


KITCHEN = """This room is called the kitchen. In it, you see: 
\tthe agent
\ta substance called air
\ta stove, which is turned on. On the stove is: a metal pot (containing liquid chocolate).
\ta freezer. The freezer door is open. In the freezer is: a tin cup (containing solid unknown substance C).
\ta blast furnace, which is turned off. The blast furnace door is closed. 
\ta glass cup (containing a substance called ice)
\ta blue box (containing nothing)
You also see:
\tA door to the outside (that is open)"""
MELTING = ("Your task is to measure the melting point of solid unknown substance C, which is located around the kitchen. "
           "First, focus on the thermometer. Next, focus on the solid unknown substance C. If the melting point of solid "
           "unknown substance C is above -10.0 degrees celsius, focus on the orange box. If the melting point of solid "
           "unknown substance C is below -10.0 degrees celsius, focus on the yellow box. The boxes are located around the kitchen.")


def test_perceiver_reads_the_melt():
    """world-scienceworld step 1b: the state of matter the text says, one name through the melt, the
    task's threshold; a thermometer's measurement typed; parts and connections one spelling."""
    p = perceive.perceive(KITCHEN, "In your inventory, you see:\n\ta thermometer, currently reading a temperature of 10 degrees celsius",
                          "the thermometer measures a temperature of 35 degrees celsius")
    a = set(p["atoms"])
    assert "state(stove,on)" in a and "in(metal_pot,stove)" in a and "in(chocolate,metal_pot)" in a and "matter(chocolate,liquid)" in a
    assert "in(unknown_substance_c,tin_cup)" in a and "matter(unknown_substance_c,solid)" in a and "open(freezer)" in a
    assert "state(blast_furnace,off)" in a and "closed(blast_furnace)" in a and "in(ice,glass_cup)" in a and not any(x.startswith("matter(ice") for x in a)
    assert "reads(thermometer,n10)" in a and p["events"] == ["said(measured)"] and perceive.measured(p["message"]) == 35
    assert p["labels"]["unknown_substance_c"] == "solid unknown substance C" and p["labels"]["chocolate"] == "liquid chocolate"
    assert perceive.task_atoms(MELTING) == ["task(melting,unknown_substance_c,orange_box,yellow_box)", "threshold(m10)"]
    flipped = MELTING.replace("above -10.0", "BELOW").replace("below -10.0", "above 150.0").replace("BELOW", "below 150.0")
    assert perceive.task_atoms(flipped) == ["task(melting,unknown_substance_c,yellow_box,orange_box)", "threshold(n150)"]   # the text's order
    assert perceive.connection("anode on battery is now connected to terminal 1 on blue wire") == ("battery_anode", "blue_wire_terminal_1")
    assert perceive.name("cathode in red light bulb") == perceive.name("red light bulb cathode") == "red_light_bulb_cathode"
    assert perceive.vocabulary(["anode on battery", "battery anode", "cup containing mercury", "substance in cup", "tin cup", "liquid chocolate", "chocolate"]) == [
        "battery_anode", "chocolate", "tin_cup"]


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
        assert "connected(battery_anode,blue_wire_terminal_1)" in r   # the result line's spelling, owner-first (opus's step 1 N2)
        assert "score" not in h.ports()["task"]                    # a second channel, kept from the brain (opus's step 1 N1)
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


def test_a_melting_gold_path_wins_through_the_host(tmp_path):
    """measure-melting-point-unknown-substance 0: the substance keeps its name through the melt, its
    matter turns solid → liquid, each thermometer use is measured(S, nN) on the perceived name (the
    command says "solid unknown substance c") for ONE beat, as said/1 (the architect's ruling on opus's
    step 1b N3: no stale value), and the verdict is a focus on the task's box."""
    from baseline import command_event
    pkg, _ = gen_instance.generate("measure-melting-point-unknown-substance", 0, str(tmp_path))
    h = SwHost(pkg)
    try:
        r = h.reading()
        assert "task(melting,unknown_substance_c,orange_box,yellow_box)" in r and "threshold(n150)" in r
        seen, temps, counts, beats = set(), [], {}, []
        for a in h.gym.call("gold")["gold"]:
            h.on_event(command_event(a), ())
            r = h.reading()
            seen |= {k for k in r if k.startswith("matter(unknown_substance_c")}
            temps += [e for e in h.events if e.startswith("measured(")]
            assert not any(k.startswith("measured(") for k in r)          # never a standing atom
            if h.done:
                break
            for line in h.tick(counts) or []:                             # the beat hands it in, the next takes it back
                atom, n = line[1:].rsplit(" ", 1)
                counts[atom] = counts.get(atom, 0) + (int(n) if line[0] == "+" else -int(n))
            beats.append({k for k, n in counts.items() if n > 0 and k.startswith("measured(")})
        assert h.won and h.score >= 100, (h.score, h.message)
        assert seen == {"matter(unknown_substance_c,solid)", "matter(unknown_substance_c,liquid)"}
        assert temps and all(t.startswith("measured(unknown_substance_c,n") for t in temps)
        assert all(len(b) <= 1 for b in beats) and sum(1 for b in beats if b) == len(temps)   # each one beat, one at a time
        assert "focused(yellow_box)" in r and h.labels["unknown_substance_c"] == "liquid unknown substance C"
    finally:
        h.gym.close()


def test_a_qualified_referent_resolves_over_the_perception():
    h = SwHost.__new__(SwHost)
    h.atoms = {"in(metal_pot,stove)", "in(tin,metal_pot)", "in(glass_cup,table)", "in(water,glass_cup)", "holds(thermometer)"}
    assert h.resolve("substance in metal pot") == "tin" and h.resolve("substance in cup") == "water"
    assert h.resolve("thermometer in inventory") == "thermometer" and h.resolve("cup containing water") == "glass_cup"
    assert h.resolve("cup containing water", contents=True) == "water"     # a thermometer used on it measures the water (opus's step 1b N2)
    assert h.resolve("liquid tin") == "tin" and h.resolve("lead") == "lead"

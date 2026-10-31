"""The real game's checkpoints and replay (world/nh_gym.py save, load, replay; nh_host snapshot, restore): the seed makes a start
or a restore + the same keys the same game. Each game here has its own player name, so none touches the page's."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "world"))
from nh_gym import EVERY_TURNS, Gym   # noqa: E402
from nh_tty import GAME, OPTIONS, Game   # noqa: E402

BUILT = pytest.mark.skipif(not os.access(GAME, os.X_OK), reason="no game: minihack/nethack/build.sh")
WALK = ["E", "SEARCH", "S", "W", "N", "NE", "SEARCH", "SW", "OPEN", "E", "SE", "NW", "KICK", "W", "E", "S", "WAIT", "N", "PICKUP", "SEARCH"]


def game(tmp_path, player, seed=3, **more):
    g = Gym()
    g.open(replay=dict({"seed": seed, "checkpoints": str(tmp_path / player), "player": player}, **more))
    return g


def walk(g, n):
    """n steps of the walk: each step's atoms, and how many keys had gone by its end."""
    atoms, marks = [], []
    for i in range(n):
        out = g.step(WALK[i % len(WALK)])
        atoms.append(sorted(out["atoms"]))
        marks.append(len(g.log))
    return atoms, marks


@pytest.fixture
def games():
    made = []
    yield made
    for g in made:
        if g.game:
            g.game.forget()


def test_a_checkpoint_is_due_at_a_new_level_and_every_so_many_turns():
    g = Gym()
    g.at_dlvl, g.at_turn = 1, 100
    assert not g.due(1, 100 + EVERY_TURNS - 1)
    assert g.due(1, 100 + EVERY_TURNS)
    assert g.due(2, 101)


def test_the_replay_is_off_for_the_page():
    g = Gym()
    assert g.seed is None and g.dir is None
    with pytest.raises(ValueError):
        g.save("x")


@BUILT
def test_the_seed_makes_the_dungeon(tmp_path, games):
    a = game(tmp_path, "nhseeda", seed=3)
    games.append(a)
    b = game(tmp_path, "nhseedb", seed=3)
    games.append(b)
    c = game(tmp_path, "nhseedc", seed=4)
    games.append(c)
    assert a.perceive()["atoms"] == b.perceive()["atoms"]
    assert a.perceive()["atoms"] != c.perceive()["atoms"]


@BUILT
def test_two_replays_from_a_checkpoint_see_the_same_game(tmp_path, games):
    """The design's test: 50 recorded steps, and from the checkpoint twice over, every step's atoms identical (monsters and pet too)."""
    g = game(tmp_path, "nhreplay", every=10 ** 6)
    games.append(g)
    first, marks = walk(g, 50)
    keys = list(g.log)
    assert g.where()["checkpoint"] == "start" and g.where()["keys_since"] == keys
    with open(tmp_path / "nhreplay" / "start.keys") as f:
        assert len(f.readlines()) == len(keys)
    for _ in range(2):
        g.load("start")
        at, seen = 0, []
        for m in marks:
            seen.append(sorted(g.replay(keys[at:m])["atoms"]))
            at = m
        assert seen == first
        assert g.log == keys                     # a replay leaves the log it found


@BUILT
def test_the_game_goes_on_from_a_save_as_from_a_load(tmp_path, games):
    g = game(tmp_path, "nhsave", every=10 ** 6)
    games.append(g)
    walk(g, 5)
    before, number = g.perceive()["atoms"], g.games
    assert g.save("here")["atoms"] == before and g.games == number
    assert (tmp_path / "nhsave" / "here.sav").exists() and g.log == []
    on, _ = walk(g, 15)
    g.load("here")
    assert walk(g, 15)[0] == on


@BUILT
def test_a_walk_checkpoints_itself_and_a_replay_stays_short(tmp_path, games):
    g = game(tmp_path, "nhauto", every=5)
    games.append(g)
    named = [g.step(a).get("checkpoint") for a in ["SEARCH"] * 12]
    assert len([n for n in named if n]) == 2
    assert g.where()["checkpoint"].startswith("auto-") and g.where()["turn"] - g.at_turn < 5


@BUILT
def test_a_game_that_ended_comes_back(tmp_path, games):
    g = game(tmp_path, "nhdead", every=10 ** 6)
    games.append(g)
    start = g.perceive()["atoms"]
    g.keys("#quit\r")
    g.keys("y")
    assert g.step("N")["done"] and g.over
    assert g.load("start")["atoms"] == start and not g.over


@BUILT
def test_two_games_share_no_save(tmp_path, games):
    a = game(tmp_path, "nhonea")
    games.append(a)
    b = game(tmp_path, "nhoneb", seed=4)
    games.append(b)
    a.save("x")
    b.save("x")
    was_a, was_b = a.perceive()["atoms"], b.perceive()["atoms"]
    a.load("x")
    b.load("x")
    assert a.perceive()["atoms"] == was_a and b.perceive()["atoms"] == was_b and was_a != was_b


@BUILT
def test_the_host_restores_a_snapshot_to_the_surprise_point(tmp_path):
    """Over the real gym child: snapshot() = the checkpoint + the keys since; restore() loads and replays; a probe's steps after it
    never happened. Closing leaves no save behind."""
    import nh_host
    level = {"replay": {"seed": 3, "checkpoints": str(tmp_path / "cp"), "player": "nhhost", "every": 10 ** 6}}
    h = nh_host.NhHost.__new__(nh_host.NhHost)
    h.level, h.gym, h.cmap, h.key, h.seed = level, nh_host.NhGym(level), None, None, 1
    h.t, h.beat, h.actions, h.pending_events, h.handed, h.done = 0, 0, [], [], [], False
    try:
        for a in WALK[:8]:
            h._take(h.gym.call("step", action=a), fresh=False)
        snap = h.snapshot()
        assert snap["checkpoint"] == "start" and snap["keys_since"]
        here = sorted(h.atoms)
        for a in WALK[8:14]:
            h.gym.call("step", action=a)
        h.restore(snap)
        assert sorted(h.atoms) == here and getattr(h, "divergences", 0) == 0
    finally:
        h.gym.close()
    assert not Game(OPTIONS.replace("name:agent", "name:nhhost")).saves()

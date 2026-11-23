"""The terrain memory's numpy reference (docs/TERRAIN-MEMORY.md v2) on synthetic SPR frames: the kerb gate (a real step
with floor on both sides vs a floor that sinks smoothly with range), the rolling window, forgetting by distance, movers.
The recordings' checks (§10) are run by percept's tools/terrain_checks.py on chair replays."""
import math

import pytest

np = pytest.importorskip("numpy")
from semantic_world.terrain import FLOOR, KERB, Params, TerrainMemory  # noqa: E402

RES, N = 0.10, 160
O = -0.5 * N * RES + 0.5 * RES


def frame(elev_fn, cls_fn=None, band_fn=None, reach=4.0):
    """A base_link SPR frame: cells ahead within `reach` m observed, elevation from elev_fn(x, y) (m)."""
    x, y = np.meshgrid(O + np.arange(N) * RES, O + np.arange(N) * RES)
    seen = (x > 0.6) & (x < reach) & (np.abs(y) < 1.5)
    e = elev_fn(x, y)
    cls = np.where(seen, FLOOR if cls_fn is None else cls_fn(x, y), 0).astype(np.uint8)
    band = np.where(seen, 1 if band_fn is None else band_fn(x, y), 0).astype(np.uint8)
    return {"observed": np.where(seen, 0, 255).astype(np.uint8), "class": cls,
            "class_conf": np.where(seen, 230, 0).astype(np.uint8), "height_band": band,
            "elevation": np.where(seen, np.round(e * 100), -32768).astype(np.int16),
            "points": np.where(seen, 3, 0).astype(np.uint8), "sigma_z": np.where(seen, 3, 255).astype(np.uint8),
            "cams": np.where(seen, np.where(y > 0, 1, 2), 0).astype(np.uint8), "res": RES, "ox": O, "oy": O}


def run(m, f, frames=8, dt=0.2):
    for i in range(frames):
        m.update(f, (0.0, 0.0, 0.0), i * dt, source="mono")
    return m.publish((0.0, 0.0, 0.0))


def cell(x, y):
    return int(round((y - O) / RES)), int(round((x - O) / RES))


def test_a_real_kerb_is_a_kerb():
    out = run(TerrainMemory(), frame(lambda x, y: np.where(x > 2.0, 0.15, 0.0)))
    kerbs = out["class"][:, :][out["class"] == KERB]
    assert len(kerbs) >= 10
    assert out["class"][cell(2.0, 0.0)] == KERB or out["class"][cell(2.1, 0.0)] == KERB
    assert out["class"][cell(1.2, 0.0)] == FLOOR and out["class"][cell(3.0, 0.0)] == FLOOR


def test_a_floor_sinking_with_range_is_no_kerb():
    # the teacher's open-ground bias: the floor read 15 % -> 50 % too far = elevation falling to -0.4 m at 2 m
    out = run(TerrainMemory(), frame(lambda x, y: np.where(x > 1.0, -0.4 * (x - 1.0), 0.0)))
    assert (out["class"] == KERB).sum() == 0


def test_the_network_kerb_class_alone_is_floor():
    out = run(TerrainMemory(), frame(lambda x, y: 0 * x, cls_fn=lambda x, y: np.where(np.abs(x - 1.5) < 0.2, KERB, FLOOR)))
    assert (out["class"] == KERB).sum() == 0


def test_the_window_rolls_with_the_chair():
    m = TerrainMemory()
    f = frame(lambda x, y: np.where(x > 2.0, 0.15, 0.0))
    for i in range(6):
        m.update(f, (0.0, 0.0, 0.0), 0.2 * i)
    m.update({**f, "observed": np.full_like(f["observed"], 255)}, (1.0, 0.0, 0.0), 1.4)   # moved 1 m, saw nothing
    out = m.publish((1.0, 0.0, 0.0))
    # the step (odom x 2.0) is now 1.0 m ahead of the chair
    assert out["class"][cell(1.0, 0.0)] == KERB or out["class"][cell(1.1, 0.0)] == KERB


def test_forgetting_by_distance():
    m = TerrainMemory()
    f = frame(lambda x, y: 0 * x)
    for i in range(5):
        m.update(f, (0.0, 0.0, 0.0), 0.2 * i)
    w0 = m.fused()["weight"].max()
    empty = {**f, "observed": np.full_like(f["observed"], 255)}
    for k in range(1, 13):                    # 6 m along x, 0.5 m a frame, 0.2 s a frame: still in the window, fading
        m.update(empty, (0.5 * k, 0.0, 0.0), 1.0 + 0.2 * k)
    F = m.fused()
    mid = np.isfinite(F["dist_since"]) & (F["dist_since"] > 5.5)
    assert mid.any() and F["weight"][mid].max() < 0.5 * w0
    for k in range(13, 31):                   # on to 15 m: what was passed > 10 m ago carries no weight (or is gone)
        m.update(empty, (0.5 * k, 0.0, 0.0), 1.0 + 0.2 * k)
    F = m.fused()
    old = np.isfinite(F["dist_since"]) & (F["dist_since"] > 10.0)
    assert not old.any() or F["weight"][old].max() < 0.05 * w0


def test_a_remembered_elevation_keeps_its_mean_while_driving():
    m = TerrainMemory()
    f = frame(lambda x, y: 0.12 + 0 * x)
    for i in range(5):
        m.update(f, (0.0, 0.0, 0.0), 0.2 * i)
    empty = {**f, "observed": np.full_like(f["observed"], 255)}
    for k in range(1, 9):                     # 2 m driven without seeing: the mean stays, the sigma grows
        m.update(empty, (0.25 * k, 0.0, 0.0), 1.0 + 0.2 * k)
    F = m.fused()
    e = F["elevation"][np.isfinite(F["elevation"])]
    assert len(e) and np.allclose(e, 0.12, atol=1e-9)


def test_a_walker_leaves_no_trail():
    m = TerrainMemory()
    for i in range(10):
        wx = 1.5 + 0.13 * i                   # a person crossing at 1.3 m/s, 0.1 s a frame
        f = frame(lambda x, y: 0 * x, cls_fn=lambda x, y: np.where(np.hypot(x - wx, y) < 0.25, 9, FLOOR),
                  band_fn=lambda x, y: np.where(np.hypot(x - wx, y) < 0.25, 6, 1))
        m.update(f, (0.0, 0.0, 0.0), 0.1 * i)
    f = frame(lambda x, y: 0 * x)
    for i in range(10, 22):                   # 1.2 s more with the walker gone
        m.update(f, (0.0, 0.0, 0.0), 0.1 * i)
    out = m.publish((0.0, 0.0, 0.0))
    assert ((out["height_band"] & 6) > 0).sum() == 0
    assert (out["class"] == 9).sum() == 0

# The structured perception representation: the contract between perception and the rest (spec PROPOSAL v0, 2026-11-12)

> **Moved (2026-11-12):** the maintained copy is in the Perotheia organisation, perotheia-packages/spr `docs/SPR.md` (the user: autonomous driving is Perotheia; the runtime there is Theia, not ROS 2). This copy is frozen.

**Status: a proposal, drafted by pascal on the user's word (2026-11-12): "we need intermediate Structured
Perception Representations. its perception output abstraction. from it data forks into 1) semantic map and
2) dynamic trajectory planner ... nicely integrate it into carla stack and wc stack ... also as testable
interface for perception that we dont need to drag rest of the stack". Nothing here is built. It is the one
interface shared by road/docs/CARLA-STACK.md (the driving stack) and metis-wheelchair docs/PERCEPTION.md (the
chair's perception); where those two name perception's outputs, this document is the authority.**

The idea comes from AirLab's "Structured Perception Representations for Off-road Dynamics Learning"
(SpatialBEV, CoRL 2026, arXiv 2610.22900; read 2026-11-12, §11). What is taken is the SHAPE: one ego-centred
structured map between perception and what plans. What is not taken is its content as it stands (§1.2, §11).

## 0. What it is

One message per perception frame, `nina_msgs/PerceptionFrame` (the SPR), holding everything perception
claims about the world at one capture time: a layered ego-centred grid, the static objects, the movers, and
the ego's own terrain reading. Two consumers read it and nothing else of perception's:

```
cameras (chair)  ─┐                         ┌─> semantic map: fuses over time, lifts to zones and levels ─> behaviour
CARLA truth      ─┼─> producer ─> SPR ──────┤
a recorded file  ─┘                         └─> dynamic planner: terrain under the wheels, now ───────────> trajectory
                                                 (obstacles and predictions still come through the semantic map)
```

## 1. Principles

1. **One contract, any producer.** The chair's perception, the CARLA adapter reading ground truth, and a
   replayed file all emit the same message. A consumer cannot tell which, except by the `source` field.
2. **Named physical layers only.** Every layer has a name, a unit and a definition that a ground truth can be
   rendered for. No opaque feature channels: AirLab's map carries 32 foundation-model feature channels beside
   its terrain channels, which suits a dynamics model learned end to end and defeats an interface that must be
   tested and versioned across producers. A producer may keep features internally.
3. **A frame has no memory.** The SPR says what was seen at ONE capture time (a producer may fuse a few
   frames to de-noise, never to remember). Persistence, prediction and "it was there a minute ago" belong to
   the semantic map alone. Two components that both accumulate will disagree.
4. **Unknown is a value.** Every layer distinguishes "seen, and it is X" from "not seen". A layer the producer
   does not make at all is ABSENT from the message, which is a third thing. Consumers read unknown and absent
   conservatively (§4).
5. **Confidence is part of the claim.** Each layer carries a confidence the producer stands behind and the
   tests measure (§8), not a decoration.
6. **Small and fixed-size.** The message must be cheap on the chair's board and trivial to record: plain
   arrays, no variable-length features.
7. **Versioned.** `version` in the header; a layer is added by a minor version and never changes meaning.

## 2. The message

```
# nina_msgs/msg/PerceptionFrame.msg
std_msgs/Header header        # stamp = CAPTURE time of the frame (not publish time); frame_id = "base_link"
uint16 version                # this document: 0
uint8  source                 # 0 perception, 1 simulator truth, 2 replay
string profile                # "wc" or "road" (§2.1)
nina_msgs/GridSpec grid       # resolution [m], width, height [cells], origin of cell (0,0) in base_link
nina_msgs/GridLayer[] layers  # §2.2; each: name, dtype, scale, offset, unknown value, data (row-major)
nina_msgs/StaticObject[] objects   # §2.3
nina_msgs/Mover[] movers           # §2.4
nina_msgs/EgoTerrain ego           # §2.5
nina_msgs/ProducerHealth health    # per sensor: frame age, dropped, soiling; share of unknown cells per sector
```

The grid is in `base_link` (x forward, y left, CARLA-STACK §3), levelled by gravity: the grid's plane is
horizontal through the ground contact under `base_link`, so a slope shows in the elevation layer and not as a
tilted grid.

### 2.1 Profiles

| profile | grid | range | for |
|---|---|---|---|
| `wc` | 160 x 160 at 0.10 m | 8 m around the chair | the wheelchair (PERCEPTION.md) |
| `road` | 200 x 200 at 0.40 m | 40 m around the car, the cell size AirLab uses | the driving stack |

A profile fixes the grid and which layers are REQUIRED. A consumer states the profile and layers it needs and
refuses a frame that lacks them.

### 2.2 Grid layers

| layer | type and unit | meaning | unknown | required |
|---|---|---|---|---|
| `observed` | uint8 | frames since a sensor last saw the cell (0 = this frame; 255 = never) | 255 | wc, road |
| `class` | uint8 enum | what occupies the cell: floor / road, kerb, stairs-or-drop, ramp, wall, door, glass, furniture, person, vehicle, mobility equipment, vegetation, other obstacle | 0 | wc, road |
| `class_conf` | uint8, 0..255 | confidence of `class` | 0 | wc, road |
| `height_band` | uint8 bits | which bands are occupied: ground, low (to 0.4 m), body (to 1.2 m), overhang (above) | 0 | wc |
| `elevation` | int16, cm | height of the supporting surface above the grid's plane | -32768 | road; wc when the front pair gives it |
| `elevation_conf` | uint8 | confidence of `elevation` | 0 | with `elevation` |
| `slope_x`, `slope_y` | int8, 0.5° | the surface's slope along x and y, from the producer's own plane fit (not for the consumer to differentiate a noisy elevation) | -128 | wc, road |
| `step` | int8, cm | the largest height discontinuity at the cell: + a step up (kerb, threshold), - a drop (hole, stair down) | -128 | wc, road |
| `surface` | uint8 enum | paved, tiles, carpet, gravel, grass, soil, wet, snow-or-ice, grating | 0 | wc; road optional |
| `roughness` | uint8, mm rms | short-wave unevenness (cobbles, roots) | 255 | optional |

"Holes, bumps, unknown objects to pass around" are these layers read together: a hole is `step` < 0, a bump
is `step` > 0 with `class` floor or road, an unknown object is `class` other obstacle with a `height_band`.

### 2.3 Static objects

Per object: a frame-local id, a tracking hint (the producer's own id when it has one; the semantic map does
the real association), the class distribution over the enum (uint8 per class), an oriented box in
`base_link`, an existence confidence, and how the box was obtained (ground contact / two-view / hull over
frames / truth), because the consumer weighs them differently. This is PERCEPTION.md §3a's output.

### 2.4 Movers

Per mover: class, pose and velocity in `base_link` with a 3 x 3 covariance of position and heading, the
footprint box, the producer's track id. The former `/world/movers` (`nina_msgs/MoverArray`) is this list.

### 2.5 The ego's own terrain reading

What the vehicle feels, which is exact where the cameras are weakest: pitch and roll from the IMU (the slope
and cross-slope under the wheels), their rates, and a vibration level (roughness under the wheels). The
dynamic planner uses it to check the grid's `slope` at the origin and to adapt friction and speed limits.

### 2.6 Size

`wc`: 25,600 cells x about 10 bytes = 256 kB a frame, 3.8 MB/s at 15 Hz. `road`: 40,000 cells x about 12
bytes = 480 kB, 9.6 MB/s at 20 Hz. On one host this is shared memory or an intra-process topic; between
hosts the layers compress well (mostly unknown or flat).

## 3. Producers

| producer | where | how each layer is made |
|---|---|---|
| the chair's perception | metis-wheelchair docs/PERCEPTION.md | `class`, `height_band`: the network and the lift; `step`, `elevation`, `slope` AHEAD: the front pair's two-view geometry (a plane fit and its residual), to about 4 m; elsewhere `step` from the semantic edge (kerb, stairs) with low confidence and `elevation` unknown; `surface`: a head of the network (later); `ego`: the IMU |
| the CARLA adapter, from truth | road/docs/CARLA-STACK.md §6 | `class` from the semantic-segmentation cameras or the map; `elevation`, `slope`, `step` from the depth cameras or downward ray casts against the map's geometry; objects and movers from the actors; confidence at its maximum; then cut to what the sensors could see (range and occlusion) so the truth is the truth of an observer |
| replay | a recorded directory (§8) | the frames as they were recorded, stamped in the replay's clock |

For CARLA most terrain layers are placeholders (flat, paved) until the cases that need them are driven:
ramps, kerbs, a stop on the shoulder. Which CARLA towns have usable kerb and slope geometry is not checked.

## 4. How a consumer must read it

- `observed` = 255, or a layer's unknown value: not traversable for planning at speed; the semantic map keeps
  what it believed and ages it.
- A REQUIRED layer absent: the frame is refused and counted; the consumer holds its last state and the
  stack's stale rules apply (CARLA-STACK §3: 300 ms, 1 s).
- An OPTIONAL layer absent: the consumer's conservative default (surface unknown → the lowest friction class
  it plans for).
- Confidence below the consumer's bound is read as unknown, never as the opposite value.
- `header.stamp` is the capture time: consumers predict from it, they do not assume it is now.

## 5. Consumer 1: the semantic map

The semantic world (metis-worlds/libs/semantic-world) is the memory and the lift:

- **Fusion over time.** Per cell and per object, the two rules PERCEPTION.md §3a takes from SuperMap:
  geometric consistency in log-odds (confirmed / occluded / seen through) and the categorical label update
  with the producer's confusion matrix. The SPR's confidences are the measurement weights.
- **Lifting to what behaviour reads.** Cells become zones and finite readings: a `kerb` edge with its height
  class (passable / passable slowly / not), a `hole` or `drop` zone, a `bump`, a `ramp` with its slope class,
  an `unknown object` to pass around with its clearance, a `rough` or `slippery` stretch. These are the level
  atoms the family reads (the road domain's and the chair's), so the geometric layers end here and behaviour
  never sees a number.
- **Prediction** of the movers, as today.

## 6. Consumer 2: the dynamic planner

The constrained trajectory planner (PLANNER.md §3: the OCP over a lane corridor) gains a terrain variant. It
reads the terrain layers from the SPR directly (they are metric and fresh) and the obstacles, predictions and
rules from the semantic map (they need memory):

- **Sampled under the wheels.** The terrain is read at the wheel contact points along each candidate
  trajectory, not at the body's centre (the one idea taken from AirLab's dynamics model: it samples its map
  at tyre-track points). For the chair: the two drive wheels and the castors.
- **Hard constraints.** `step` above the vehicle's climbable height, or below its droppable height, in the
  direction of travel: the cell is closed. Static stability: pitch and roll from `slope_x`, `slope_y` along
  the path stay inside the tip-over margins of the vehicle's file, with the rider's mass.
- **Speed limits along the path.** From the down-slope (stopping distance grows), the cross-slope, the
  `surface` friction class and `roughness`: v_max(s) enters the OCP as a bound, as the lane's limit does.
- **Costs.** Roughness and cross-slope as comfort terms; unknown terrain as a cost that grows with speed.
- **The lane variant is the flat special case:** on a `road` frame with flat placeholders the terrain terms
  vanish and the planner is today's.
- **A physical model first.** At the chair's speeds the dynamics that matter are tipping, kerb climbing,
  braking downhill and traction by surface: a model with a handful of measured parameters (wheelbase, track,
  centre of mass with rider, wheel radii, friction per surface class). AirLab learns its dynamics because slip
  at 10 m/s on an ATV is not modelled by hand; a learned residual on top is a later option, trained from the
  chair's own logs against `ego`.

## 7. Where it sits in the two stacks

| | wheelchair | CARLA / driving |
|---|---|---|
| producer | perception on the AI-64 | `nina_carla_adapter`, from truth (a placeholder for a perception stack) |
| topic | `/perception/frame` | `/perception/frame` |
| semantic map | zones for paths, plazas, kerbs, ramps, drops | LaneMap from OpenDRIVE plus the frame's obstacles and movers |
| planner | the terrain variant | the lane variant; terrain terms idle until the ramp / kerb / shoulder cases |
| behaviour | the chair's family over the lifted readings | the road family, unchanged |

Changes this makes to the other documents: CARLA-STACK §3 and §6: the adapter publishes `/perception/frame`
and `/world/movers` becomes its `movers`; PERCEPTION.md §2: `/perception/semantic_grid`, `/world/objects`
and `/world/movers` become the layers, `objects` and `movers` of the one frame, and `/perception/free_space`
is derived from it by a small node for Nav2's costmap.

## 8. Testing at the interface (the reason to have one)

- **The ground-truth renderer.** From CARLA (and wc-sim) the same frame is rendered from truth, cut to the
  sensors' view. Perception's frame is compared with it layer by layer: per-class recall and precision of
  `class` by range band; error of `step`, `elevation`, `slope` where truth has them; calibration of every
  confidence (of the cells claimed at 0.9, are nine in ten right); the share of cells wrongly claimed
  observed. On the real chair the reference is the recording rig's depth sensor (PERCEPTION-TRANSFER.md §3).
- **Record and replay.** A recording is a directory: `frames/<stamp>.npz` (the layers), `objects.jsonl`,
  `movers.jsonl`, `ego.jsonl`, `meta.yaml` (version, profile, grid, producer, calibration hash). The semantic
  map and the planner run from it with no camera, no network and no simulator. Data is collected and kept AT
  this interface: a new perception is scored on old recordings' raw video, a new planner on old frames.
- **Fault injection.** A filter between producer and consumers: drop a layer, blank a sector, add noise to
  `step`, delay frames, lower confidences. The pass criterion is the stack's: it slows or stops, it never
  drives into what it was told is unknown.
- **Contract tests,** run on every frame in CI and optionally at run time: the header's version and profile;
  required layers present with the grid's size; unknown values only where `observed` says unseen or the
  confidence is zero; no cell both `floor` and `body`-occupied; stamps increasing.
- **Scenario cards.** A card (SCENARIO-CARD.md) can carry a recorded or synthetic frame sequence as its
  input, so behaviour and planner cards run without a world.

## 9. Steps

- **R0 the message and the tools**: `nina_msgs` definitions, the recorder, the replayer, the contract tests,
  a viewer (layers as images). No producer yet: hand-made frames.
- **R1 CARLA truth producer** in the adapter, `road` profile, flat terrain; the semantic bridge and the lane
  planner read the frame in place of `/world/movers`. Pass: S4's cards (CARLA-STACK §8) give the same verdicts.
- **R2 the chair's producer**: PERCEPTION.md's levels L0 / L1 emit the `wc` frame; scored against the
  renderer in simulation and the rig on recordings.
- **R3 terrain**: `step`, `slope`, `elevation` from the front pair; the planner's terrain variant on recorded
  frames of a kerb, a ramp and a drop; then on the chair.
- **R4 the terrain cases in CARLA**: a ramp, a kerb, a stop on the shoulder, with the `wc` stack in CARLA.

## 10. Risks and open items

1. **Terrain from cameras is the weak layer.** AirLab builds its terrain channels from a LiDAR. The chair has
   two-view geometry only in the front 100° and the rear 58°, and to a few metres. `step` and `slope` to the
   sides will be low-confidence or unknown; the planner must be safe on that (it is: unknown closes cells).
2. **Small hazards against the cell size.** A 5 cm hole or a 3 cm threshold is below a 10 cm cell's footprint:
   `step` is a per-cell maximum so that it is not averaged away, and whether the network sees it at all is
   R3's measurement.
3. **Freezing the interface too early.** v0 is deliberately small; `surface` and `roughness` are optional
   until a producer can make them.
4. **Two profiles** double the test matrix; the alternative, one grid with a variable cell size, is worse.
5. **Latency is visible here.** With IP cameras the capture stamp can be 100 to 300 ms old (PERCEPTION.md
   §10.1): consumers must predict from the stamp, and the fault filter's delay test exists for this.
6. **Not decided:** whether the frame travels as one ROS message or as shared memory with a small header
   message; who owns the class enum when the road and the chair need different classes (one enum with both).

## 11. What was read (2026-11-12)

AirLab, "Structured Perception Representations for Off-road Dynamics Learning" (SpatialBEV), Nye, Triest,
Sivaprakasam, Adu, Scherer, Wang; CoRL 2026; arXiv 2610.22900; project page theairlab.org/spatial-bev-dynamics.
An ego-centred map, 100 m x 100 m at 0.40 m, of terrain channels (elevation, surface normals, step height,
slope) and visual-foundation-model features; built from a Velodyne LiDAR and a stereo camera with
SuperOdometry's poses; a recurrent dynamics model that samples the map at tyre-track points and predicts the
vehicle's state 5 s ahead; MPPI planning on a full-size ATV at 8 to 10 m/s with a laptop GPU. Code: "coming
soon", none released. The paper evaluates the dynamics and the driving; it does not evaluate the
representation on its own, so the testability argued for in §8 is ours to show. Channel counts and the
planner's figures were read from a summary of the paper's later sections, not verbatim.

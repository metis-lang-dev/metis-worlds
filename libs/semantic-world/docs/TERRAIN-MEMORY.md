# Terrain memory: the semantic world's short-term map of ground and seen objects

Status: design, decided by the user 2026-11-23 ("go with B on A"). Not built yet.
Owner of the design: pascal (architect). Producer side: percept. Consumers: chariot (planner, wc / road domain, viz).

## 1. Why

The perception representation (SPR, `spr/docs/SPR.md` §1.3) has no memory by design: a frame says what was
seen at one capture time, and "persistence belongs to the semantic map alone". That per-cell memory was never
built. Today the planner and the viz read single frames, and it shows:

- real structures (a kerb, a wall) flicker from frame to frame, so the stop point jumps;
- the grid is sparse: a network answers on a coarse raster, so most ground cells have no value in one frame
  (teacher v2 at stride 8: 91 % of the grid empty; with stride 4 + the footprint splat: 42 %);
- the floor in the legs' shadow is known only through a narrow planner-side memory of free cells;
- a box seen as 50-70 obstacle cells never becomes one stable object.

The semantic world already remembers THINGS (tracks, zones, places: `bayes`, `mixed`, `occupancy`). This
document adds the missing half: a short-term memory of GROUND GEOMETRY and of static things on it.

## 2. What it is, and what it is not

It is a chair-centred, rolling, short-term map: a few seconds and a few metres of fused evidence.

It is NOT SLAM. No global map, no loop closure, no relocalisation, nothing stored between sessions, nothing
reused when the chair comes back to a place. Terrain and seen objects are remembered while they are inside the
window and recent; then they are forgotten. A thing seen again later is a new thing.

## 3. The frame: a rolling window on the odometry frame

- **Axes** are the odometry frame's (x, y fixed to the ground, z up). The map does not rotate with the chair:
  rotating a grid resamples it and blurs it every tick.
- **Origin** follows the chair in whole cells. When `base_link` has moved one cell, the window shifts by one
  cell: rows / columns that leave are dropped, the ones that enter are empty. No interpolation, ever.
- **Extent** 16 m x 16 m at 0.10 m (160 x 160), the wc profile of the SPR grid, so one layout serves both.
  The road profile keeps its own (200 x 200 at 0.40 m).
- **Pose source**: the 50 Hz odometry feed the controller uses (contracts `Odometry`: `base_link` pose and
  twist in the odom frame, own stamp; on the real chair filled by MavCtrl from ArduRover). Each perception
  frame is placed with the odometry pose AT ITS CAPTURE STAMP, not at arrival.
- **Drift is bounded by forgetting, not corrected.** Wheel odometry drifts by 1-2 % of the distance driven.
  Evidence therefore ages by DISTANCE TRAVELLED as well as by time (§6), so nothing older than about 10 m of
  travel carries weight: at that point the drift is still within one or two cells. Older evidence is also
  blurred by the drift it may have accumulated (its kernel grows, §5), so stale structure fades instead of
  standing sharply in the wrong place.
- **Published in `base_link`** for the consumers (a rotation + shift of the window at publish time, nearest
  cell), with the stamp of the latest frame fused and the odometry pose used.

## 4. What a cell holds (variant A: the layered grid)

| quantity | representation | SPR layer it fuses |
|---|---|---|
| elevation | mean + variance (a 1-D Kalman state) | `elevation`, `elevation_conf` |
| occupancy | log-odds per height band (floor / low / body / overhead) | `class`, `height_band`, `observed` |
| class | Dirichlet counts over SprClass (14) | `class`, `class_conf` |
| ground use | Dirichlet counts over SprGroundUse | layers 12 / 13 |
| step, slope | DERIVED from the fused elevation and its variance, never fused themselves | `step`, `slope_*` |
| bookkeeping | time and travelled distance since last seen, number of observations, source bits (gt / mono / stereo) | - |

Labels stay labels (the user's rule): the map carries classes with their evidence; what the chair may do on a
class is the domain's policy table, not the map's.

## 5. The update (variant B: Bayesian kernel inference on that grid)

A measurement is one lifted point of a frame: position, class probabilities, a range sigma, and its ground
footprint (pixel angle x range). It updates not one cell but every cell within a support radius, weighted by a
sparse kernel k(d) that is 1 at the point and 0 at the support radius.

- **Support radius** = max(footprint radius, 1.5 cells), enlarged by the odometry drift bound of old evidence.
  A dense near measurement stays sharp; a sparse far one honestly covers the ground its pixel covers.
- **Class**: alpha_c += k * w * p_c. The expected class and its variance come out in closed form
  (Dirichlet), so "kerb, but on thin evidence" is a number a consumer can read.
- **Elevation**: a Kalman update with measurement variance sigma_z^2 / (k * w). A single far point moves a
  well-observed cell very little.
- **Occupancy**: + k * w * l_hit in the band of the point.
- **Free space**: the ray from the camera to the point lowers the occupancy of the bands it passes THROUGH
  (seen through) and marks the floor cells it ends on as observed. A cell believed occupied that rays keep
  passing through is cleared: geometric consistency, the rule taken from SuperMap in PERCEPTION.md §3a.
- **w** is the producer's confidence. A stereo range (SprRangeSet, small variance) weighs far more than a
  monocular one; the two are never merged before this point.
- **Own body**: cells under the chair's footprint and in the legs' shadow receive no measurement, so they
  simply keep what was fused while the chair approached them. This replaces the planner's narrow
  observed-free memory with the general one.

## 6. Forgetting

- Evidence decays towards the prior with time AND with distance travelled since it was last seen: half-weight
  after about 10 s or 5 m for static structure (parameters).
- Mover classes (person, vehicle, mobility) are not terrain: their cells decay within about 1 s, and the
  thing itself lives as a track (§7). A walker leaves no trail of occupied cells.
- Cells that leave the window are gone.

## 7. Seen objects

Static things seen on the ground (a box, a pole, furniture) are kept as short-lived tracks in the same rolling
frame, next to the movers' tracks the range tracker already keeps: position, extent, class counts, existence.

- Born from a stable connected patch of the FUSED grid (not from one frame), so a 0.6 m box at 2 m is one
  object, not flickering cells.
- Updated by the range channel (stereo / mono observations) and by the patch.
- Dropped when existence decays or when they leave the window. They are not reused: no re-identification, no
  association with something seen earlier and forgotten.

## 8. What comes out

- **The fused grid**, in the SPR grid layout plus variance and age layers, published in `base_link` at the
  perception rate (5 Hz). The planner reads it instead of the single frame (a parameter; the car's default
  unchanged). The terrain layers stay metric; the domain still reads only levels and zones.
- **Edges**: kerb edges and walls extracted from the fused grid as polylines with a height class
  (`SprBoundaryLine` already exists). A kerb is a step that holds along an edge with floor on both sides at
  consistent elevations AND exceeds max(0.10 m, 2 sigma of the fused elevation). A floor that sinks smoothly
  with range is a depth-scale error, not a kerb.
- **Static objects** (§7) into the object list the planner, the EGG and the domain already read.
- **Viz**: the fused map and the single frame as two named streams; the page says which one is shown.

The producer stays memoryless. Two components that both accumulate would disagree (SPR.md §1.3).

## 9. Where it lives

In the semantic world, on the planner's path: a C++ node in the stack (working name `TerrainMemory`), fed by
the SPR grid chunk, the range feed and the odometry feed. This library carries the design and a numpy
reference implementation that serves as the oracle for the C++ node's tests (the method percept used for
SprStereo).

Cost estimate (to be measured): about 30 floats per cell x 25,600 cells = 3 MB; 4 cameras x 96 x 72 points x
a 3 x 3 to 5 x 5 kernel = 0.25-0.7 M cell updates per frame, a few milliseconds on one core.

## 10. First acceptance (qualitative, one run per card: the budget rule)

On the chair cards with the teacher, fused vs single frame:

1. a real kerb / wall is present in the fused map in every frame while in view (no flicker), and the stop
   point does not jump;
2. the floor in the legs' shadow is known after the chair has driven up to it, and unknown at a cold start;
3. the box ahead is one object from about 4 m to the stop;
4. a crossing walker leaves no occupied trail older than 1 s;
5. after 15 m of driving, structure passed more than 10 m ago carries no weight;
6. the car cards are bit-identical with the node off.

## 11. Variants considered and not taken

- **C. A Gaussian per cell** (the normal-distributions-transform occupancy map): compact, sharp surfaces at
  coarse cells, exact recursive updates. Its strength, surface orientation, is covered here by extracting
  edges from the fused grid. Kept as the fallback if 0.10 m cells prove too costly on the board.
- **D. Free semantic Gaussians indexed by a kd-tree** (GaussianFormer-style): adaptive and memory-light, but
  the published methods are learned per-frame networks, not incremental filters; free space is not
  represented; the planner would splat them back to cells; and merging / splitting / pruning adds failure
  modes. A research note, not a plan.
- **E. Things only** (what the library had): right for movers, wrong for ground.

## 12. Sources

- Gan et al., Bayesian Spatial Kernel Smoothing for Scalable Dense Semantic Mapping: https://arxiv.org/pdf/1909.04631
- Wilson et al., Convolutional Bayesian Kernel Inference for 3D Semantic Mapping: https://arxiv.org/pdf/2209.10663
- Miki et al., Elevation Mapping for Locomotion and Navigation using GPU: https://arxiv.org/pdf/2204.12876
- Erni et al., MEM: Multi-Modal Elevation Mapping for Robotics and Learning: https://arxiv.org/pdf/2309.16818
- OHM: GPU Based Occupancy Map Generation (NDT-OM in practice): https://arxiv.org/pdf/2206.06079
- Huang et al., GaussianFormer: https://arxiv.org/pdf/2405.17429

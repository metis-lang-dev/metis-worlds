# The planner stack: levels, the semantic reference, the NLP, the CommonRoad loop (design, the architect, 2026-11-06)

**Status: DESIGN, planner-loop s-0dcc5ed1 step 1. The user's direction (2026-11-06): the long-horizon planner is developed together with the road domain as the regulation judge, against CommonRoad's native loop and tooling; a BSD planner is the baseline; the trajectory planner is an SB-2023-style nonlinear optimisation, OUR code over CasADi + IPOPT (LGPL accepted for the planner; code generation later when needed); the long and the short horizon are clearly separated, as Nav2 separates them; "on strategy we inline": the behaviour layer IS the road domain's command, no decision module and no discrete variables in the optimiser. Lanelets are dropped: the reference comes from our semantic LaneMap (useless for the chair anyway). 0 USD.**

## 1. The levels

| level | horizon | owner | input | output | Nav2 |
|---|---|---|---|---|---|
| route | the trip | commonroad-route-planner (BSD) now; the LaneMap's own graph later | the map, start, goal | the lane sequence to the goal | planner server |
| behaviour | the next zone / the next change, 3–10 s | the road family (metis-catalog domains/road, the planner member, change.llp, levelk.llp) | the semantic world's facts | ONE command per beat: accel / keep / brake(R) / yield / inch / change(side) / change_back | BT navigator |
| trajectory | 3–5 s receding, dt 0.1 | OUR NLP (§3); the baseline commonroad-reactive-planner (BSD) | the reference (§2) + the corridor + the predictions | states and controls for the horizon, the first executed | controller server |
| safety | the next 2 s | the responder member + the restrictor (RSS proper response; metis-worlds road/world/restrict.py) | the fold's bounds | an acceleration cap the trajectory may not exceed | collision monitor |
| sequencing | per beat | the director (tick protocol, spec 15) | grants | who holds the controls | the BT's ticks |

The separation rule: the behaviour level decides WHAT (lane, go / yield, pace), the trajectory level decides HOW over its horizon, the safety level CAPS. No level re-decides another's output: the optimiser never chooses a lane or a yield, the law never emits a curvature. The chair runs the same five with its members (nav, wc) and a corridor instead of lanes.

## 2. The reference trajectory from the semantic map (the user's question, 2026-11-06)

The reference is built every beat from the LaneMap (filled by the perception side, SUMO or CARLA or CommonRoad's recording through the exerciser) and the command. Four pieces:

1. **The path.** The route's lanes as a chain of centrelines; the ego's lateral offset decays onto the centre over 2 s. A `change(side)` adds a spline from the current centre to the sibling's centre over the change length (v × 3 s, min 30 m); `change_back` the reverse. The chair takes the same object from its corridor or the Nav2 global path.
2. **The speed profile** along the path: the target speed under the lane's limit; a stop at the yield / brake distance (the zone line, the walker's crossing, the lead's RSS gap); a following speed held at the RSS gap behind a lead; the goal window's arrival speed when a window exists (CommonRoad: land in [t_min, t_max]). The profile is the command made numeric; nothing is decided again downstream.
3. **The corridor.** The lane's edges as half-spaces per step, minus the predicted boxes of the other movers over the horizon (the semantic world's prediction kernel, the same the fold uses); the change and the oncoming pass WIDEN the corridor by the law's decision, never by the optimiser. That is the inlined strategy.
4. **The initial guess** = the reference itself sampled at dt on the path with the profile: x, y, ψ from the path, v from the profile, a and δ from the profile's slope and the path's curvature. A feasible reference solves in a few iterations; an infeasible one (the corridor pinches) returns the reference's clipped version and the beat's command stands (the safety level still caps).

The reference builder is the one place the lanelet ever was: today it reads the LaneMap, so a CommonRoad scenario, a SUMO net and a CARLA town give the same reference object.

## 3. The NLP (our version of SB-2023's OCP; the shape kept, the decision module replaced by §2)

- **State** x = (px, py, ψ, v) at the rear axle; **control** u = (a, δ); kinematic single-track, RK4 at dt 0.1 over N = 30–50 steps (receding; SB-2023 shot the whole goal window at once: we keep that as the long-horizon CHECK run, not the control loop).
- **Constraints**: dynamics; |a| ≤ a_max, a ≤ the safety level's cap (hard, per step, from the restrictor: the shield INSIDE the problem, and the restrictor still clips the executed control after it: belt and braces); |δ| ≤ δ_max, |δ̇| ≤ rate; v ≥ 0; Kamm's circle; the corridor's half-spaces per step; a terminal constraint v = 0 at the stop point when the profile stops.
- **Cost**: tracking of the reference (position, heading, speed, weighted), uᵀRu, ΔuᵀR_ΔΔu; a goal-window term when one exists.
- **Solver**: CasADi Opti + IPOPT, warm start from §2.4 (the reference) and then from the previous solution shifted; C code generation of the functions when the loop needs it (the user has done it: a wrapper is needed, doable); IPOPT stays the development solver, a codegen-able solver (FATROP, acados) is the embedded pairing later.
- **The chair**: the unicycle model in the same problem; the corridor from free space; the same cost.
- **Size**: the OCP ~400 lines, the reference builder ~600–900, the loop + tests ~300 (opus's reading of SB-2023: steps/sb2023-reading-opus.md). No code of SB-2023's is copied (unlicensed): the method is a few equations and the design above.

## 4. The CommonRoad native loop (the benchmark, no SUMO)

The scenario's lanelet network → the LaneMap through the exerciser's observation adapter; the recorded obstacles as movers; the planning problem's initial state and goal; the family drives through the five levels; CommonRoad's drivability checker (collision, kinematic feasibility), its cost functions and the goal-in-window test are the oracle beside our measures; a solution file is written per run so TUM's own evaluation reads it. The set: the catalog's 192 CommonRoad cards (their scenario ids from the checkout at the pin), then the recorded sets whole on panzer. CI nightly over the recorded set as the catalog's is.

## 5. Steps (planner-loop)

1. The architect: this design (done with this file); the interface spec: `Command` (the beat's), `Reference` (path, profile, corridor, guess), `Plan` (states, controls, feasible, cost), the oracle's row.
2. opus: the Python 3.11 venv (the reactive planner's requires_python) with commonroad-io, commonroad-route-planner, commonroad-reactive-planner, commonroad-drivability-checker, commonroad-clcs, all BSD, the licenses listed in the report; `road/planner/cr_bench.py`: a planning problem from the checkout → route → the baseline reactive planner natively → solution → the checker's row; the table over the 192 cards' scenarios; then the family's command as the planner's setpoints (desired velocity, stop position, reference path per lane) = the first long-horizon composition; the baseline's table beside it.
2b. opus: the SB-2023 ORIGINAL as a bench column (§6.2): its own venv, our wrapper `road/planner/sb_bench.py`, the same oracle row and the decision record per scenario over the same subset. BEFORE step 3: it is the comparison's target and costs a run of existing code.
3. opus: `road/planner/reference.py` (§2) and `road/planner/ocp.py` (§3) over CasADi + IPOPT; the loop in the native CommonRoad world; the table over the same set; the restrictor as the cap. Tests: the reference on three maps (straight, T-junction, merge); the OCP's feasibility on the reference; the stop constraint; a corridor pinch.
4. The architect: the ruling on the FOUR tables (baseline, composition, SB-2023 original, ours; §6): goals reached in their windows, collisions 0 with the recorded obstacles, feasibility, runtime per beat; the paper note (the levels as the certification argument: the law decides inside the safe set, the optimiser realises inside the corridor, the restrictor caps).
5. Later subjects: Nav2 (the controller server runs our OCP; the collision monitor is the restrictor), the CARLA host, the chair's corridor.

## 6. The four tables and the comparison (the user's direction, 2026-11-07)

**The user's word (2026-11-07):** the baseline is the original BSD planner's. Next, our planner AND the original SB-2023 planner are added on the same subset, and the work is the comparison SB-2023 → ours: the two share the NLP's shape (§3), so every difference between their rows is the decision layer's (SB's reachability decision module against the road domain's command over the semantic reference). Those differences are the problems the road domain introduces; they are classified first and worked after. The first analysis matters more than speed, and it is the architect's, not delegated.

### 6.1 The tables
| table | planner | decision layer | status |
|---|---|---|---|
| baseline | commonroad-reactive-planner (BSD), native | the package's own (shortest route, initial speed) | DONE: road/planner/tables/baseline-a0f668a.md (subset v2: 25 rows, 15 region goals, 4 reached) |
| composition | the reactive planner | the family's command as setpoints (§5 step 2, deliverable 3) | next (opus) |
| SB-2023 original | Kochdumper's MotionPlanner @ 5434d05, low-level `Optimization` | its reachability decision module (steps/sb2023-reading-opus.md §4) | step 2b (opus) |
| ours | reference.py + ocp.py (§2, §3) | the road domain's command over the LaneMap reference | step 3 (opus) |

The composition is a smoke of the family's command in the native loop (the reactive planner confounds it); the comparison that carries the ruling is SB-2023 vs ours.

### 6.2 The SB-2023 bench column (step 2b)
- The repository has NO licence (all rights reserved): read, study and RUN on the bench; never copied, never a dependency of anything shipped (road/docs/planner-licenses.md gets its line: "bench column only"). Its linearisation planner pulls cvxopt (GPL): not on our path, and a bench venv anyway (the user, 2026-11-07).
- A clone outside the tree at the pin (sha recorded with its SOURCE line beside the other downloads under /bigdata/datasets/commonroad/), its own venv (the README's Python 3.8 through uv; commonroad-io 2023.1 and the rest as pinned there), road/.venv-sb2023 git-ignored.
- Our wrapper `road/planner/sb_bench.py` imports its modules directly (main.py's `bool(sys.argv[2])` never selects the optimiser), runs the decision module + the `Optimization` planner under the repository's defaults (one shot over the goal window; collision_avoidance off), plus one extra column with collision_avoidance on (one flag), and writes the same solution.xml + row.json so cr_bench's oracle produces the same row. Same subset, same defaults rule (§5 step 2 review: no tuned yamls).
- **The decision record, per scenario, for SB AND for ours** (the comparison's data): the lane(let) sequence per step, the speed profile v(t), the stop points, the steps of the lane changes, the horizon, the solver's status / iterations / time, and the trajectory (solution.xml). The composition records the family's command per beat the same way (lane decisions, pace / yield / stop setpoints), so the decision diff SB vs family can start before ours exists.

### 6.3 The classification (the architect's first pass; refined on the data)
Per scenario the diff is read in this order, and the first class that explains the row is the row's class:
- **W world / oracle**: a conversion or checker artefact (time-only goals, lane maps, the step-0 kappa_dot mass, initial contact) → a bench item, not a planner finding.
- **D decision**: the family's command differs from SB's choice (lane, go / yield, pace). Two sub-kinds: D-law = ours yields or slows where SB drives through AND the oracle's rule monitors side with ours (SB knows only the speed limit) → counted FOR the road domain, not a defect; D-gap = ours decides worse by the oracle (misses the window, blocks, changes lanes needlessly) → a law or world gap, a record of the catalog's kind.
- **R reference**: the same decision, a different reference (path geometry from the LaneMap vs lanelet centrelines; the speed profile not window-fitted) → a reference.py item.
- **C corridor**: feasibility or collision from our corridor vs SB's free space → a corridor builder item.
- **S solver**: the same reference, a different solve (warm start, options, receding vs one shot) → an ocp.py item.
The four-table analysis (step 4) lists every row with its class and the items per class; D-gap items become briefs for the road domain, the rest planner items. Order: step 2b (SB column) → composition (deliverable 3 + iface) → the architect's decision diff D on SB vs the family (while step 3 runs) → step 3 (ours) → the four-table analysis.

## 7. The user's decision 2026-11-07 night: our planner reads lanelets directly (option 2)

**The question.** The baseline and SB columns ran on the CommonRoad toolchain alone; the cr2sumo conversion served only to give the family a LaneMap, whose single reader today is a SUMO net file. The conversion is lossy (opposite lanelets get their own nodes: no oncoming lane; the harvest's other ten losses), so every loss would land in the comparison as a false problem of the road domain. Two ways out were put to the user: (1) a direct lanelet → LaneMap adapter, the family kept in the loop (the architect's recommendation, §4 as written); (2) our planner reading lanelets directly, as SB does, CommonRoad-only for now. **The user chose (2).**

**What (2) means for the steps (the staged ladder).**
- **Step 3 = ours on lanelets.** `road/planner/lanelet_ref.py` builds the reference (§2's four pieces) from the CommonRoad lanelet network directly: the route from commonroad-route-planner (BSD), the path from the route's centrelines with the lateral decay, the speed profile window-fitted under the lanelets' limits (SB's idea, our code), the corridor from the lanelet polygons minus the recorded obstacles' predicted boxes per step (constant velocity, as SB), the initial guess. `road/planner/ocp.py` is §3 as designed (steering-rate bound, input weights, Kamm, corridor half-spaces, the receding loop with warm start). The loop runs in the 3.11 planner venv on the CommonRoad toolchain; solution.xml + row.json + record v1 (mode receding, lanelet per step) through cr_bench's oracle; the tables over subset v2 and sb100 beside SB (init) and SB (vlim). No road law, no LaneMap, no SUMO in this step: the comparison SB vs ours isolates the S, R and C classes (§6.3) with the road domain out of the loop by construction.
- **Step 3b (later, the user's go): the family as the decision layer** over the same NLP: the command → the reference's lane sequence, stops and pace (the composition's mapping, planner-compose ffaa522), which needs the family's facts over this map: either the lanelet → LaneMap adapter (option 1, then taken) or the facts read from the lanelet network. That step isolates the D class. §1–§4 stand as the target architecture; §7 is the order of construction.
- **The chair and CARLA** are served by the LaneMap path (§2) when step 3b brings it; the lanelet reader of step 3 is CommonRoad-only and says so in its header.


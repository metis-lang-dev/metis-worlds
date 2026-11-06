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
3. opus: `road/planner/reference.py` (§2) and `road/planner/ocp.py` (§3) over CasADi + IPOPT; the loop in the native CommonRoad world; the table over the same set; the restrictor as the cap. Tests: the reference on three maps (straight, T-junction, merge); the OCP's feasibility on the reference; the stop constraint; a corridor pinch.
4. The architect: the ruling on the three tables (baseline, composition, ours): goals reached in their windows, collisions 0 with the recorded obstacles, feasibility, runtime per beat; the paper note (the levels as the certification argument: the law decides inside the safe set, the optimiser realises inside the corridor, the restrictor caps).
5. Later subjects: Nav2 (the controller server runs our OCP; the collision monitor is the restrictor), the CARLA host, the chair's corridor.

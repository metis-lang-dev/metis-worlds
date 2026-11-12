# The CARLA stack: CARLA 0.9 (UE4) + ROS 2 Humble + C++, the C++ client library for control and sensors, our planner, no Nav2 (design, the architect, 2026-11-07; the simulator changed 2026-11-11)

> **Moved (2026-11-12):** the maintained copy is in the Perotheia organisation, perotheia-packages/carla_ws `docs/CARLA-STACK.md` (the user: autonomous driving is Perotheia; the runtime there is Theia, not ROS 2). This copy is frozen.

**Status: DESIGN for the user's own implementation. The user's choices (2026-11-07): a C++ ROS 2 controller; OUR OCP planner (road/planner, PLANNER.md §3, parity with SB-2023 shown); no Nav2, our original stack (PLANNER.md §1's five levels); interfaces independent of CARLA and Autoware, so the planner never knows whether CARLA, a real car or another simulator tracks its trajectory; a later port to Adaptive AUTOSAR (theia) for a faster runtime. Package names are the user's (nina_*).**

**Changed 2026-11-11 (the user): CARLA 0.9 on UE4, not 0.10.0.** We have no hardware for UE5, so 0.10.0 and its native ROS 2 interface (DDS inside the server) are out. Simulator I/O is CARLA's own C++ client library (LibCarla's client, `carla::client`) for BOTH directions: the sensors are read through it and the commands are applied through it, inside `nina_carla_adapter`. No DDS in the server and no `carla-ros-bridge`: the adapter is the only process that speaks CARLA at run time, beside the scenario manager. The version to pin is the latest 0.9 release that S0 passes on our GPU (0.9.15 proposed; not yet tried here).

## 0. The one thing to validate first (before much code)
The C++ client's I/O in synchronous mode, above all its COMMAND PATH and the sensors' frame alignment. Experiment S0 (§8) decides two things. (a) The command: the adapter turns `AckermannDriveStamped` into `carla::rpc::VehicleAckermannControl` (`Vehicle::ApplyAckermannControl`; the client API has had Ackermann control since 0.9.14); if the server's Ackermann controller does not follow within a tick or is not repeatable, the adapter falls back to throttle / brake / steer (`VehicleControl`) through an inverse longitudinal model. (b) The sensors: each sensor's `Listen` callback arrives on a client thread; the adapter must publish every sensor of a tick with that tick's sim-time stamp, none dropped or reordered. Nothing above the command topic or the sensor topics changes with either outcome: that is the point of the contract in §3.

## 1. Principles
1. **Core logic as plain C++ (or Python) libraries, ROS as a shell.** No `rclcpp` type in a controller, planner or adapter library; the node is a thin wrapper that converts messages to the library's structs and back. This is what makes the AUTOSAR port a re-wrapping and not a rewrite: each library becomes a theia Functional Cluster, each topic a service interface (`.art` modelling later), the rates become the cluster's cycles.
2. **The semantic world is the only adapter boundary** (as in the road domain). CARLA fills the LaneMap from its OpenDRIVE map (a third reader beside the SUMO net and the lanelet adapter) and the movers from CARLA's actors (ground truth first, perception later). The family never sees CARLA.
3. **Ownership of time.** The scenario manager owns the simulation tick (synchronous mode); everything else is driven by `/clock`. The Live's beat is the tick (the beat hold: a paused manager holds the beat).
4. **The planner's output is the authoritative trajectory contract** (`nina_msgs/Trajectory`, §3), with velocity, acceleration, curvature and time, sampled at the planner's dt. `nav_msgs/Path` is a visualization output only.
5. **The safety level caps, never re-decides.** The restrictor's acceleration bound is applied inside the planner (the trajectory it publishes already respects it) AND as a hard clamp in the controller (belt and braces, PLANNER.md §3).
6. **Copies, not deps**; licences: Autoware's `mpc_lateral_controller` is Apache-2.0 (adapting its model and solver shape into our C++ with the notice is fine); CARLA's client library is MIT and is LINKED (built from the pinned tag's source), not copied; the planner stays ours.

## 2. Components (the user's selection, placed in our five levels)
| level (PLANNER.md §1) | component | language | package | does |
|---|---|---|---|---|
| simulator I/O | CARLA 0.9 server (UE4) + its C++ client library | server; C++ (LibCarla client) | `nina_carla_adapter` | the adapter reads the sensors and the world snapshot through the client and publishes them with `/clock`; it applies the Ackermann command through the client |
| scenario / time | scenario manager | Python (CARLA PythonAPI) | `nina_scenario_manager` | spawns actors from a scenario CARD (SCENARIO-CARD.md v2), configures sensors, owns the tick (synchronous mode, fixed_delta 0.05), resets, writes the card's measures |
| ego state | the same adapter | C++ (CARLA client) | `nina_carla_adapter` | `/localization/odometry`, `/vehicle/status` (actual steering angle, gear, wheel speeds), `/tf`, ground-truth movers for the semantic world until perception exists |
| perception → semantic world | CARLA world adapter | Python | `nina_semantic_bridge` (road/world/carla_world.py) | OpenDRIVE → LaneMap; actors → movers (range + occlusion as the road's perception); fills the semantic world every beat |
| behaviour | the road family | metis-agent Live + road host | (metis-agent, metis-catalog) | ONE command per beat: accel / keep / brake(R) / yield / inch / change / change_back |
| trajectory | our OCP planner | Python (CasADi + IPOPT; codegen later) | `nina_planner_bridge` (road/planner) | reference (§2 of PLANNER.md) from the LaneMap + the command; the OCP; publishes `nina_msgs/Trajectory` at 10 Hz |
| safety | the restrictor | Python (planner side) + C++ clamp (controller side) | in the two above | acceleration cap from the RSS fold; the controller's hard limits |
| control | trajectory controller | C++ | `nina_vehicle_controller` | lateral linear MPC (kinematic bicycle + steering delay, adapted from Autoware's mpc_lateral_controller) + longitudinal PID with acceleration and jerk limits; publishes `AckermannDriveStamped` at 20 Hz |
| command interface | `ackermann_msgs` | C++ | — | `AckermannDriveStamped` |
| messages | `nina_msgs` | IDL | `nina_msgs` | Trajectory, TrajectoryPoint, VehicleStatus, Limits (§3) |

Starting points, as the user weighed them: Autoware's MPC lateral controller (mature, linear MPC, kinematic + dynamic bicycle, steering delay; Autoware-specific msgs and packages to strip, so an adaptation, not a drop-in); `ackermann_nlmpc` (compact NMPC, but Jazzy and a Python wrapper: not the Humble/C++ baseline). Bring-up ladder for the controller: pure pursuit + PID first (a day, proves the whole loop), the MPC second (the deliverable).

## 3. The contracts (ROS 2 topics; all stamped in sim time, `use_sim_time: true`)
| topic | message | publisher | rate |
|---|---|---|---|
| `/clock` | `rosgraph_msgs/Clock` | adapter (the world snapshot's sim time, once per tick) | 20 Hz |
| `/carla/ego/front_camera/image` | `sensor_msgs/Image` | adapter (client sensor) | 20 Hz |
| `/carla/ego/lidar/point_cloud` | `sensor_msgs/PointCloud2` | adapter (client sensor) | 10–20 Hz |
| `/carla/ego/imu`, `/carla/ego/gnss` | `sensor_msgs/Imu`, `NavSatFix` | adapter (client sensor) | 20 Hz |
| `/localization/odometry` | `nav_msgs/Odometry` | adapter (ground truth now; a localization later) | 20 Hz |
| `/vehicle/status` | `nina_msgs/VehicleStatus` | adapter | 20 Hz |
| `/planning/command` | `nina_msgs/Command` (diagnostic: the family's command, for the record and the page) | Live / road host | per beat |
| `/planning/reference_path` | `nav_msgs/Path` (visualization) | planner bridge | 10 Hz |
| `/planning/trajectory` | `nina_msgs/Trajectory` (AUTHORITATIVE) | planner bridge | 10 Hz |
| `/safety/limits` | `nina_msgs/Limits` | planner bridge (the restrictor's cap) | 10 Hz |
| `/vehicle/ackermann_cmd` | `ackermann_msgs/AckermannDriveStamped` | controller | 20 Hz |
| `/tf` | `map → odom → base_link`; `base_link` at the REAR AXLE centre | adapter | 20 Hz |

```
# nina_msgs/msg/TrajectoryPoint.msg   (frame: header.frame_id of the Trajectory, normally "map";
#  x, y, heading refer to the REAR-AXLE centre, the OCP's state; the controller converts if its model wants the CoG)
float64 x
float64 y
float64 heading          # rad, ENU, counter-clockwise from +x
float64 curvature        # 1/m, signed (+ left)
float64 velocity         # m/s along the path
float64 acceleration     # m/s^2 along the path
float64 time_from_start  # s, relative to header.stamp; strictly increasing; the planner's dt (0.1 s)

# nina_msgs/msg/Trajectory.msg
std_msgs/Header header   # stamp = the state time the plan starts from; frame_id = "map"
uint32 sequence          # the planner's cycle counter (the record's k)
nina_msgs/TrajectoryPoint[] points

# nina_msgs/msg/VehicleStatus.msg
std_msgs/Header header
float64 speed            # m/s, longitudinal, signed
float64 steering_angle   # rad at the front wheels (actual)
float64 acceleration     # m/s^2 longitudinal (measured or differentiated)
int8 gear                # -1 reverse, 0 neutral, 1 forward
bool emergency_brake

# nina_msgs/msg/Limits.msg      (the safety level's cap; the controller clamps to it, never above its own static limits)
std_msgs/Header header
float64 accel_max        # m/s^2
float64 decel_max        # m/s^2, positive magnitude
float64 speed_max        # m/s
float64 jerk_max         # m/s^3
```
Rules of the contract: the controller interpolates the trajectory by sim time (`header.stamp + time_from_start`), never by index; it tracks the LAST trajectory received while it is fresh; stale rules: no new trajectory for 300 ms → hold speed and decelerate at the comfort limit along the last path; 1 s → `decel_max` to a stop (emergency_brake true in the status). A trajectory with fewer than 5 points or non-increasing time is rejected with a diagnostic, the previous one kept.

## 4. Timing
| component | rate | trigger |
|---|---|---|
| CARLA simulation | 20 Hz (fixed_delta 0.05, synchronous) | the scenario manager's `world.tick()` |
| scenario manager | one tick per step | its own loop; waits for the planner's ack when `lockstep: true` |
| semantic bridge + family (the Live) | per beat = per tick (the fold at 20 Hz is cheap; the family's command changes rarely) | `/clock` |
| planner bridge (our OCP) | 10 Hz | every second tick; must return within 100 ms, else the previous trajectory stands and the miss is counted |
| controller | 20 Hz, synchronized with the tick initially | `/clock` edge; later free-running at 50 Hz on a real car |
Two modes from day one: `lockstep` (the manager ticks only after the planner acked the beat: deterministic, the testing page's pause holds the beat: metis-agent beat-hold) and `realtime` (the manager ticks on the wall clock; misses are measured). The catalog runs in lockstep; the controller is tuned in realtime.

## 5. The controller (nina_vehicle_controller)
- **Library** `nina_control` (no ROS): `LateralMpc` (kinematic bicycle in the error frame: lateral error, heading error, steering state with a first-order steering delay; linear time-varying MPC over 2–3 s, QP by OSQP or qpOASES; constraints |δ| ≤ δ_max, |δ̇| ≤ rate; cost on errors, δ, Δδ; the curvature feed-forward from the trajectory point) and `LongitudinalPid` (speed error → acceleration command, with feed-forward from the trajectory's acceleration; clamped by `Limits` and the static limits; a jerk limiter on the output; anti-windup; stop logic: below 0.3 m/s with a stop target → hold brake).
- **Node** `controller_node`: subscribes trajectory, odometry, status, limits; publishes `AckermannDriveStamped` {steering_angle, steering_angle_velocity, speed (the interpolated target), acceleration (the PID's output), jerk}; a `/controller/diagnostics` with lateral / heading / speed errors per cycle (the measures of §8).
- **Bring-up:** pure pursuit (lookahead = max(3 m, 0.8 s · v)) + the same PID behind a parameter first; the MPC replaces it when the loop is proven.
- **Adapted from Autoware's mpc_lateral_controller:** the model, the delay compensation and the QP formulation; its `autoware_*` msgs replaced by `nina_msgs`, its `vehicle_info` by a yaml of our own (wheelbase, steering ratio, δ_max, rate, mass for the dynamic model later). Attribution in the package's NOTICE.

## 6. The adapter (nina_carla_adapter, C++ client, libcarla): the only simulator I/O
- **Library** `nina_carla_io` (no ROS, principle 1): connects to the server (`carla::client::Client`), finds the ego and its sensors by role name (the scenario manager spawned them), and exposes plain structs: a tick's snapshot (sim time, frame), the sensor samples, the ego state, the movers, and `apply(command)`. The node wraps it. On another simulator or a real car this library is the part that is replaced.
- **Sensors through the client.** Each sensor actor's `Listen` callback (camera `sensor::data::Image`, lidar `LidarMeasurement`, `IMUMeasurement`, `GnssMeasurement`) runs on a client thread and only queues the sample with its frame number. The node's tick handler (`World::OnTick` or `WaitForTick`) publishes `/clock` first, then every sample of that frame converted to its ROS message with `header.stamp` = the frame's sim time; a sensor whose period is longer than the tick (lidar at 10 Hz) is simply absent on the frames it did not fire. A frame that lacks an expected sample after a timeout is published without it and counted in `/adapter/diagnostics`; nothing is ever stamped with wall time. Conversions: CARLA is left-handed (x forward, y right, z up, UE units already metres in the client API), ROS is right-handed: y and yaw negated once, here, and nowhere else.
- Publishes `/localization/odometry` (ground truth from the ego's transform + velocity, frame map, base_link at the rear axle: the CARLA bounding-box centre shifted back by `wheelbase/2` per the vehicle's physics control), `/vehicle/status` (actual steering from the wheels' physics control, speed, gear), `/tf`.
- Publishes the structured perception representation `/perception/frame` FROM TRUTH (SPR.md, 2026-11-12: the one contract between perception and the rest; here a placeholder for a perception stack): the layered grid, the static objects and the movers, cut to what the sensors could see. Until SPR.md's R1 it publishes only the movers, as `/world/movers` (`nina_msgs/MoverArray`: id, type, pose, velocity, box) for the semantic bridge until a perception stack exists; the bridge applies range and occlusion itself so the family sees what the road's perception would.
- **The command through the client** (§0): `AckermannDriveStamped` → `VehicleAckermannControl` (steer, steer_speed, speed, acceleration, jerk) applied to the ego before the next tick; parameter `command_path: client_ackermann | client_throttle` (the second: `VehicleControl` throttle / brake / steer through an inverse longitudinal model). In lockstep the manager ticks only after the adapter has applied the command of the beat.

## 7. The scenario manager (Python, CARLA PythonAPI of the same 0.9 release) and the semantic bridge
- Reads a scenario CARD (SCENARIO-CARD.md v2): map (a CARLA town; OpenDRIVE maps later through `generate_opendrive_world`), ego spawn and vehicle blueprint, actors relative to the ego with their triggers (the catalog's director logic in Python, as on SUMO), params and variants, expect and measures. Spawns, attaches the sensors (camera, lidar, imu, gnss, each with a `role_name` the adapter finds it by; no ROS flag: the adapter publishes them); the camera rig is the wheelchair's own four-camera rig (metis-wheelchair docs/PERCEPTION.md §2a: four RGB cameras of 137°, with a depth and a semantic-segmentation camera beside each for labels), read from the same `rig.yaml`, owns the tick, applies the triggers per step, writes the card's measures (collision events merged 5 s / 5 m, outside-route-lanes, goal in window, our rule monitors from the family's record) to the card's row, resets between variants. Later: a card → OpenSCENARIO writer for ScenarioRunner (SCENARIO-CARD.md's bridge).
- The semantic bridge (road/world/carla_world.py): OpenDRIVE (the town's map, `carla.Map.to_opendrive()` or the file) → LaneMap: lanes with successors, same-direction neighbours, OPPOSITE lanes, junction lanes, signs and lights as zones; the movers from `/world/movers` under range + occlusion; the semantic world's predict / update; the fold; the family's command out as `/planning/command`. This is the CARLA host of the road domain (the third host beside SUMO and the exerciser), with the same Loop.

## 8. Bring-up ladder (each a step with its pass criterion; one short report each)
- **S0 the client's I/O** (the user's validation point): the pinned CARLA 0.9 server (UE4, `-RenderOffScreen`), the adapter built against that tag's LibCarla client on the Humble host; sync mode 20 Hz over 1000 ticks: (a) the sensors: every expected sample is published in its tick with a stamp equal to the sim time (no drops, no reordering, the lidar on its own period); (b) the command: publish a 2 m/s² step `AckermannDriveStamped` and measure when the vehicle's acceleration follows through `ApplyAckermannControl` (pass: within 1 tick, every run identical in sync mode); if (b) fails or jitters → `command_path: client_throttle` and the same measurement; (c) the GPU: frame time and memory with camera + lidar, which fixes the sensor set and the release pinned. The result FIXES §0's choices.
- **S1 adapter + tf**: odometry against CARLA's truth (pass: rear-axle frame error < 1 cm, steering status within 0.5°), movers published.
- **S2 controller on canned trajectories** (a straight at 10 m/s, a 50 m-radius circle, a stop profile): pure pursuit first, MPC second; pass: lateral error < 0.3 m and speed error < 0.5 m/s on the circle, stop within 0.5 m, no jerk limit violation.
- **S3 planner bridge**: our OCP on a Town lane with the LaneMap from OpenDRIVE and a FIXED command (keep at the limit): the trajectory published at 10 Hz, tracked by S2's controller; pass: the OCP's trajectory feasible, the controller's errors as S2, 100 ms budget held on 95 % of cycles.
- **S4 the family in the loop**: the Live with the CARLA host on two cards (the straight with a static obstacle, as ZAM_Over on CARLA; a T-junction with a crosser); pass: the card's verdict equals the SUMO host's for the same card (the semantic world is the same, so the law must say the same).
- **S5 the catalog on CARLA**: the ten CARLA-origin cards of road/catalog on their own simulator; the coverage table gains a CARLA column; nightly on the GPU host.

## 9. Repository and packages
A ROS 2 workspace repository of its own (`nina_ws`, the user's naming; private like metis-wheelchair until the licence phase): `src/nina_msgs`, `src/nina_vehicle_controller` (+ `nina_control` library), `src/nina_carla_adapter`, `src/nina_planner_bridge` (Python node over the installed `road/planner` package: `pip install`, never a path), `src/nina_scenario_manager`, `src/nina_semantic_bridge` (over the installed semantic-world library and metis-agent). `colcon build`; a `docker/` with the Humble image and the pinned CARLA 0.9 release's C++ client (LibCarla built from that tag: the client and the server must be the same version) and its PythonAPI wheel for the scenario manager; CI builds and runs S2's canned-trajectory tests against a recorded odometry (no CARLA in CI); S0–S5 run on the GPU host by hand or nightly. metis-worlds keeps the design (this file), the card format and the semantic bridge's world module; nothing of CARLA's enters metis-catalog.

## 10. Risks and open items
1. The 0.9 release to pin is not chosen by a run yet: the client library must be built from the server's own tag (CARLA supports only a client and a server of the same version, and warns of a mismatch at connect), with its toolchain on Ubuntu 22.04 beside Humble's; S0 is where this is found out. The 0.9 line is UE4 and in maintenance: we take no feature that only 0.10 has. 2. GPU: UE4 is what our hardware can run, but panzer's RTX 2000 Ada 8 GB is still to be measured at 20 Hz with camera + lidar; measure in S0, reduce the sensor set or run headless (`-RenderOffScreen`) first. 2a. The scenario manager's PythonAPI wheel must exist for the Humble host's Python (3.10) in the pinned release; if not, the manager runs in its own venv or moves to the C++ client too. 2b. Sensor callbacks arrive on client threads: the frame barrier of §6 is the adapter's own code and the first place a dropped or late sample would hide. 3. Determinism: CARLA's physics is deterministic in sync mode only with fixed substepping and the same seed; record the seed and the substep parameters in every row. 4. OpenDRIVE → LaneMap is the third map reader: junction geometry and lane sections need the same tests as the lanelet adapter (three maps + an oncoming lane). 5. The 10 Hz planner budget: IPOPT in Python may miss it on junction corridors; the codegen path (CasADi C code, FATROP/acados later) is the planned remedy, not a tighter horizon. 6. Ground truth vs perception: the semantic bridge's range + occlusion stand in for a perception stack; the sensors are published for the later perception work and the record, not consumed yet. 7. Steering delay and actuator limits of the CARLA vehicle blueprint must be read from its physics control and put into the controller's yaml, or the MPC's delay model is wrong from day one.

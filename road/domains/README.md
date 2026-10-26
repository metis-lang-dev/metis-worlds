# road — the road domains over roles (road-world s-e812715d step 2)

The RSS world's decisions as LLP, the geometry in the host (the framework's six rules: roles not lanes, geometry in
the host, re-projection with no recompilation, generators beside the package, decisions in the logic and prices in the
ports). Moved here from metis-catalog `domains/road` (road-move, 2026-10-26: the domains beside their world); the
parked package before them is gone (its road-close scene stays pinned in metis-lang `corpus/road-close`).

| file | what |
| --- | --- |
| `capacity.llp` | the role vocabulary, one per vehicle: lead, follower, leadleft/followleft, leadright/followright, a1..a3, vru1, nextzone, the sides; the situation layer's constellations and responses |
| `responder_domain.llp`, `responder/` | the FAST member (every world step, 0.1 s): the proper response — it takes the controls on a longitudinal response or a lateral one toward a lane change's side, brakes at the asked response, stops the lateral move, hands the controls back |
| `planner_domain.llp`, `planner/` | the SLOW member (every tenth step, 1 s): the keep-table once each over roles — the safety stage (yield at a zone not the ego's, the walker, the zipper's turn) before the progress stage (lane change past a slow lead, accel with room, keep, a gentle brake behind a closing lead) |
| `road_director/` | the generic tree director (metispy iface/director_tree_domain.llp) over the one resource, the controls: priority(responder, planner), k = 2, m = 1 |
| `composition.yaml`, `tick_types.llp` | the composition (response 2), the protocol's types. No family package (tools/iface_gen.py): its cut is empty — the members share nothing but the protocol, each reads its own world-private copy |
| `eval/` | the instrument's world model of a lane change (spec/16 §10.1, `tick: ego`): the target lane's follower and lead, their intent belief, closing hazards by tick; cases gap / tight and their goldens; the level lc_risk |
| `*/cases/` | the members' stub cases, the old scenes among them: road-close, prodcat lead-lanes-free, Euro NCAP AEB VRU CPNA-25 and CPFA-50 |

The members' hosts are the road world's (`../world/road_host.py`, found through `$METIS_ROAD_WORLD`, else the world/
directory above the package):
the exerciser (`road_world.py`) or the SUMO host (step 4); the facts every host writes are `road_facts.py`, the
commands and the restrictor `restrict.py`. Each base carries its generated cancel rules (metispy
`metis.catalog.protocol_stub`); `../tests/test_domains.py` checks they are current, runs the members' cases through
the interface stub, and holds the traces (`goldens/traces/`) and the lane-change risk to their goldens (METISC;
METIS_HOME defaults to metispy's catalog for the `iface/` includes). The tree demo: `../experiments/road_tree.py`
(METIS_CATALOG = `road/`).

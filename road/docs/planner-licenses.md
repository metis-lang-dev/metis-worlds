# The planner venv's licenses (planner-loop s-0dcc5ed1 step 2)

`road/planner/setup-venv.sh` builds `road/.venv-planner` (git-ignored) on a Python 3.11.14 interpreter that uv downloads (the
user's word, 2026-11-07), from the pins in `road/planner/requirements.txt`. We copy no code from these packages and put none on
sys.path. We pip-install them and import them from the bench (`road/planner/cr_bench.py`) only. Nothing in metis-catalog or the
SDK depends on them.
I read the licenses from each installed distribution's metadata (`License`, `License-Expression`, classifiers) and from its
bundled LICENSE file, on 2026-11-07.

## The packages the brief names
| package | version | license | note |
|---|---|---|---|
| commonroad-reactive-planner | 2025.1 | BSD 3-Clause (TUM CPS) | the baseline planner; requires Python <3.12 |
| commonroad-route-planner | 2025.1.0 | BSD 3-Clause | the reference path (the lanelet route) |
| commonroad-drivability-checker | 2025.4.0 | BSD 3-Clause | collision + feasibility checks (pycrcc) |
| commonroad-clcs | 2025.2.0 | BSD 3-Clause | the curvilinear coordinate system |
| commonroad-io | 2024.3 | BSD 3-Clause | same pin as the conversion venv `road/.venv-cr` |
| commonroad-vehicle-models | 3.0.2 | BSD 3-Clause | vehicle parameters (the reactive planner's model) |
| casadi | 3.8.2 | LGPL-3.0-or-later | the user's accepted line (2026-11-06); the wheel bundles IPOPT (EPL-2.0) and MUMPS (CeCILL-C) as plugins |

## Their dependencies (transitive)
| package | version | license |
|---|---|---|
| numpy 2.4.6, scipy 1.17.1, networkx 3.6.1, shapely 2.2.0, contourpy 1.3.3, lxml 6.1.3, protobuf 3.20.2, python-dateutil 4.0.0, omegaconf 2.4.0, kiwisolver 1.5.1, cycler 0.12.1, ImageIO 2.38.1, methodtools 0.4.7, wirerope 1.0.0 | | BSD (2- or 3-Clause; numpy also 0BSD/MIT/Zlib/CC0 parts) |
| matplotlib 3.11.2 | | matplotlib license (PSF-based, permissive) |
| fonttools 4.68.0, iso3166 3.0.0, pyparsing 3.3.3, PyYAML 6.0.3, rtree 1.4.1, six 1.17.0, pillow 13.0.0 | | MIT (pillow: MIT-CMU) |
| osqp 0.6.7.post3, qdldl 0.1.9.post1, tzdata 2026.6, packaging 26.3 | | Apache-2.0 (packaging: Apache-2.0 OR BSD-2-Clause) |
| tqdm 4.70.1 | | MPL-2.0 AND MIT |
| **triangle 20250106** | | **LGPL-3.0 for the wrapper; it wraps J. R. Shewchuk's Triangle (C). Triangle's own terms restrict commercial distribution to an arrangement with the author** |
| **Polygon3 3.0.9.1** | | **LGPL for the wrapper; its metadata says the bundled GPC (General Polygon Clipper) is "free for non-commercial use only"** |

## The two not-permissive dependencies
- **Polygon3 (GPC)** is required by commonroad-drivability-checker (`polygon3>=3.0.8`). **triangle** is required by
  commonroad-reactive-planner (`triangle>=20230923`), and by the drivability checker's `triangle` extra.
- Using them in our own research bench (no distribution) is within their terms. Shipping them in a product, or in a commercial
  system, is not without the authors' terms. The planner of PLANNER.md §3 (CasADi + IPOPT) needs neither.
- The architect's or the user's word is needed before either reaches anything we distribute. Both terms must be re-checked at
  the source (GPC: the Manchester page named in Polygon3's metadata; Triangle: cs.cmu.edu/~quake/triangle.html) before any such
  step.

## Not used
SB-2023 (github.com/KochdumperNiklas/MotionPlanner) has no license: read only, nothing copied (s-0dcc5ed1 steps/sb2023-reading-opus.md).

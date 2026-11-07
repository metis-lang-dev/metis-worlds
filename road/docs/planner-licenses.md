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
**Bench only: never a dependency of our planner or of anything we ship** (the architect's ruling, 2026-11-07). The reactive-planner
venv is a research bench, untracked and never distributed, so Polygon3 and triangle may stay in it. Our planner's own requirements
are a separate file, `road/planner/requirements-ours.txt` (casadi and what our reference builder and OCP need, neither of the two),
so the boundary is a file. A veto by the user would mean replacing the drivability checker's polygon operations, not stopping.
- **Polygon3 (GPC)** is required by commonroad-drivability-checker (`polygon3>=3.0.8`). **triangle** is required by
  commonroad-reactive-planner (`triangle>=20230923`), and by the drivability checker's `triangle` extra.
- Using them in our own research bench (no distribution) is within their terms. Shipping them in a product, or in a commercial
  system, is not without the authors' terms. The planner of PLANNER.md §3 (CasADi + IPOPT) needs neither.
- The architect's or the user's word is needed before either reaches anything we distribute. Both terms must be re-checked at
  the source (GPC: the Manchester page named in Polygon3's metadata; Triangle: cs.cmu.edu/~quake/triangle.html) before any such
  step.

## The SB-2023 bench column: bench column only
- **SB-2023** (github.com/KochdumperNiklas/MotionPlanner at 5434d0559b85d3d84733d46ee1596cd5338fe549) has **no license**, so
  all rights are reserved. It is cloned on the user's word (2026-11-07) outside every repo, at
  /bigdata/datasets/commonroad/sb2023-motionplanner (SOURCE line beside it). It is **bench column only**: run and read on
  the bench, never copied, never a dependency of our planner or of anything we ship. road/planner/sb_bench.py imports it
  from the clone; nothing of it is in this tree. Its 100 scenarios (the sb100 set) stay in the clone.
- Its venv `road/.venv-sb2023` (git-ignored): CPython 3.8.20 by uv (the README's Python), at the pins of
  `road/planner/requirements-sb2023.txt` (38, a freeze of its requirements.txt resolved on 2026-11-07): commonroad-io
  2023.1, drivability-checker 2024.1, route-planner 2025.0.1, casadi 3.8.2 (LGPL-3.0+), control 0.9.4 (BSD-3-Clause),
  mat4py 0.6.0 (MIT), opencv-python 5.0.0.93 (Apache-2.0), shapely 2.0.7, numpy 1.24.4, scipy 1.10.1, matplotlib 3.7.5.
- **GPL in it:** pypoman 1.1.1 (GPL-3.0), pycddlib 2.1.8 (GPL), cvxopt 1.3.3 (GPL-3.0). These are bench-venv only (the
  user's word). Note: the Optimization planner's module imports pypoman at load, so it is on the path we run, not only
  on the linearisation path.

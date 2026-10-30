# metis-worlds — small worlds for the metis agentic loop

One repo, one world per folder (the user's decision, 2026-10-22: the world repos collapsed
into one; the worlds share the gym pattern, the package host and the experiments driver,
which move to `metis.host` / `metis.repl` in metispy under the metis-packages subject).

| folder | world | how it learns |
|---|---|---|
| [`alfworld/`](alfworld/README.md) | ALFWorld 0.4.2 (TextWorld games; AI2-THOR for frames) | the kernel acts, surprises become rules; the domain hierarchy with a director (`alfworld/docs/HIERARCHY.md`); the exploitation demo (`alfworld/docs/DEMO.md`) |
| [`minihack/`](minihack/README.md) | MiniHack 1.0.2 on NLE 1.3.0 | the small LLM agent in the loop, the domain extracted after |
| [`scienceworld/`](scienceworld/README.md) | ScienceWorld 1.2.3 (a text laboratory; Java) | hidden properties: the loop must run the experiment that reveals them (`scienceworld/experiments/REPORT.md`) |
| [`web/`](web/README.md) | (every world) | the world map: one renderer and schema, a tileset per world (`web/tiles/` is NetHack's art, its own NOTICE) |

Installing the whole stack on a fresh host (repos, system packages, the three venvs, the models, ALFWorld and its demo): [`docs/INSTALL.md`](docs/INSTALL.md).
| [`libs/semantic-world/`](libs/semantic-world/README.md) | (every world) | `semantic_world`: the semantic map, its Bayesian update, the roles bound to a world's names, the port contract — pure python, no dependency, its own pyproject and tests; installed editable by each world's `setup.sh` (and in metis-agent's venv, where the hosts run, and the metispy venv the hierarchy drivers start: `METIS_PY`, else `../.venv`). It is cut out to its own repo when the road returns |

Each world has its own `setup.sh` (a venv at `<world>/.venv`, or `.worlds/<alf|mh>` found by
walking up), `world/` (the gym child, the host, the generators), `domains/` (generated
packages and the lifted bases), `experiments/` and `tests/`. Run a world's suite with its
venv and `METISC` pointing at metis-lang's compiler, e.g.

```
METISC=../metis-lang/src/metisc ALFWORLD_DATA=../.worlds/alfworld-data ../.worlds/alf/bin/python -m pytest alfworld/tests -q
../.worlds/mh/bin/python -m pytest minihack/tests -q
python3 -m pytest libs/semantic-world/tests -q          # the library alone: no world, no game (CI runs it)
METISC=../metis-lang/src/metisc ../.worlds/sw/bin/python -m pytest scienceworld/tests -q
../metis-agent/py/.venv/bin/python -m pytest road/tests -q --deselect road/tests/test_sumo_world.py   # road: no venv of its own
```

Each world's venv (its `setup.sh`) has `libs/semantic-world` installed editable (a package: never on a
`PYTHONPATH`); a world's runtime (`<world>/world`) is reached by its path. The editable install is main's:
a branch (a worktree) that changes the library is tested in a venv with the branch's installed
(`pip install -e <worktree>/libs/semantic-world`).

Nothing here goes into metis-catalog: a world's plug code is the world's own.

History: merged on 2026-10-22 from `metis-world-alfworld` and `metis-world-minihack` with
`git subtree` (both histories kept; the old repos are archived).

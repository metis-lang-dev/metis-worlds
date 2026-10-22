# metis-worlds — small worlds for the metis agentic loop

One repo, one world per folder (the user's decision, 2026-10-22: the world repos collapsed
into one; the worlds share the gym pattern, the package host and the experiments driver,
which move to `metis.host` / `metis.repl` in metispy under the metis-packages subject).

| folder | world | how it learns |
|---|---|---|
| [`alfworld/`](alfworld/README.md) | ALFWorld 0.4.2 (TextWorld games; AI2-THOR for frames) | the kernel acts, surprises become rules; the domain hierarchy with a director (`alfworld/docs/HIERARCHY.md`); the exploitation demo (`alfworld/docs/DEMO.md`) |
| [`minihack/`](minihack/README.md) | MiniHack 1.0.2 on NLE 1.3.0 | the small LLM agent in the loop, the domain extracted after |
| [`web/`](web/README.md) | (every world) | the world map: one renderer and schema, a tileset per world (`web/assets/` is NetHack's art, its own NOTICE) |

Each world has its own `setup.sh` (a venv at `<world>/.venv`, or `.worlds/<alf|mh>` found by
walking up), `world/` (the gym child, the host, the generators), `domains/` (generated
packages and the lifted bases), `experiments/` and `tests/`. Run a world's suite with its
venv and `METISC` pointing at metis-lang's compiler, e.g.

```
METISC=../metis-lang/src/metisc ALFWORLD_DATA=../.worlds/alfworld-data ../.worlds/alf/bin/python -m pytest alfworld/tests -q
../.worlds/mh/bin/python -m pytest minihack/tests -q
```

Nothing here goes into metis-catalog: a world's plug code is the world's own.

History: merged on 2026-10-22 from `metis-world-alfworld` and `metis-world-minihack` with
`git subtree` (both histories kept; the old repos are archived).

# scienceworld — the experiments' record

## §1 The world side (world-scienceworld step 1, 2026-10-22): the gold paths through the host

The simulator's own solution of each variation, sent through the HOST command by command (a
gold line → the fired rule's event → the game's verb; `experiments/baseline.py`). What this
shows: the harness reproduces the world (score 100), the perception is stable across
variations (the same predicates), and the world's refusals are modeled (0 after the fix below).

| split | n | won | gold steps | host steps (mean) | atoms per reading (mean) | atoms max | s per variation | predicates |
|---|---|---|---|---|---|---|---|---|
| train (discovery) | 20 | 20 | 15–43 | 25.8 | 22.7 | 39 | 0.6 | 10: closed connected door focused here holds in reads state task |
| test (held out) | 10 | 10 | 15–43 | 26.4 | 23.2 | 39 | 0.7 | 10: closed connected door focused here holds in reads state task |

Both task types of the `conductivity` family (a named thing, an unknown substance) win on every
variation tried, including the held-out ones (the world's test split), by their gold path.

**What the first run taught (fixed before the table):**
- the game's `valid` list spells a referent one way ("connect agent to blue wire terminal 1")
  while the game accepts others ("connect battery anode to …"); a host pre-check against that
  list refused 4–17 gold commands per variation and lost the unknown-substance family at score
  60. The list is advisory now; a refusal is the game's own line (`said(unknown)` / `said(cant)`);
- the perceiver lower-cases names, but the game's referent is case-sensitive ("unknown substance
  B"): the perceiver keeps each name's world spelling (`labels`), the host uses it in commands;
- "a green light bulb, which is off" after a comma in a list is one item, not two.

**The perception vector** (the loop's complexity measure, LEARNING.md): 10 predicates over one
`thing` type of ~500 referents (the simulator's vocabulary, names only); a reading is 18–28 atoms;
the package declares `in(thing, thing)` and `connected(thing, thing)`, so the ground bound is
dominated by those two (≈ 2 × 500²); metisc compiles the package in 7 ms.

**What step 2's hand hierarchy must write and step 3's loop must find:** `conducts(X)` is never
in the text. The circuit — battery, two wires, a bulb, X in series — lit after a `wait`
(`state(red_light_bulb, on)`) says yes, dark says no; then `move X to <box_if_yes|box_if_no>`.

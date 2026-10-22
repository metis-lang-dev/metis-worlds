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

## §1b The melting family (world-scienceworld step 1b, 2026-10-22): the gold paths through the host

`measure-melting-point-known-substance` (chocolate, gallium, lead, mercury, tin, water) and
`…-unknown-substance` (18 lettered substances, solid or liquid at the start), each variation's gold
path through the host, as in §1 (`baseline.py --family melting`).

| split | n | won | gold steps | host steps (mean) | atoms per reading (mean) | atoms max | s per variation | predicates |
|---|---|---|---|---|---|---|---|---|
| train (discovery) | 20 | **20** | 19–94 | 48.2 | 43.9 | 52 | 1.4 | 13: closed door focused here holds in matter measured open reads state task threshold |
| test (held out) | 10 | **10** | 18–96 | 55.5 | 40.9 | 50 | 1.4 | the same 13 |

There was one refusal in 30 runs: known-substance v=2's gold opens the cupboard twice, and the
second time the game answers "The cupboard is already open." (`said(cant)`; nothing moved).

**Conductivity rerun on the changed perceiver** (one spelling per terminal, connections from
the result line, the held thermometer's reading): train **20/20**, test **10/10**, no refusals,
the same 10 predicates as §1.

**What the perception adds for melting:**
- `task(melting, S, box_if_above, box_if_below)` + `threshold(nN)`. Every one of the 552 train and
  test variations puts "above" first; the perceiver reads the sides by their words, not their
  order. Thresholds in the family are −10, 10, 50, 150 and 200 °C.
- `matter(S, solid|liquid|gas)`: the state of matter, when the name says it ("solid unknown
  substance C", "liquid chocolate"). S keeps one name through the melt, so
  `matter(unknown_substance_c, solid)` → `matter(unknown_substance_c, liquid)` is the
  observation the rule rests on.
- `measured(S, nN)`: a thermometer used on S. The result line says only the temperature; S is
  the command's referent resolved over the perception ("substance in metal pot" → what the pot
  holds).
- The verbs USE(thing, target) and EXAMINE join the card. The gold paths heat on the stove or in
  the blast furnace (activate) and cool in the freezer (move), so no other new verb is needed.

**Opus's step 1 notes, taken here:**
- N1: score and reward are gone from `ports()` and `$METIS_SW_LOG`. The host keeps them for the
  baseline only.
- N2: `focused` and `connected` come from the result line in the world's spelling, with parts
  owner-first.
- N3: the vocabulary holds one name per thing (test-conductivity 0: 495 referents → 302 names).
  Declaring only the names perceived so far is still step 3's choice.

**What step 2's hand hierarchy must write for melting, and step 3's loop must find:** the melting
point is never in the text. Put S where it heats or cools, with the device on, measure it with
the thermometer at every step, and note `measured(S, T)` the step `matter(S, …)` changes. Then
compare T with the threshold and focus on that side's box. Water is the exception: freezing
replaces "water" with "ice" (a new name, no prefix), so the change is a thing appearing in the
cup, not `matter/2` (README, findings).

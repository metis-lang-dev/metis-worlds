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
| train (discovery) | 20 | **20** | 19–94 | 48.2 | 43.3 | 51 | 1.4 | 13: closed door focused here holds in matter measured open reads state task threshold |
| test (held out) | 10 | **10** | 18–96 | 55.5 | 40.3 | 49 | 1.5 | the same 13 |

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
- `measured(S, nN)`: a thermometer used on S, an EVENT handed in for one beat, as `said/1` is: the
  reading at the beat it was taken, never a stale value; a program that wants a number measures.
  The result line says only the temperature, so S is the command's referent, resolved over the
  perception: "substance in metal pot" → what the pot holds, and "cup containing mercury" → the
  mercury, since a thermometer measures what is in the cup.
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

**opus's step 1b review (PASS) and the architect's rulings:**
- **N1, the renaming trap.** Test variations 329 and 330 are water. Freezing replaces "water"
  with "ice", so they never show a `matter/2` change, and a train rule over matter changes cannot
  reach them. That is 20% of this held-out set measuring something train never shows. **Ruling:**
  it's instance knowledge the world hides. 329/330 stay in the held-out split but are reported as
  their own row ("the renaming trap"), and the generalization number is given with and without
  them. The hand hierarchy gets no `freezes_to` fact. If the loop finds it from the text, that is
  a result to report, not a given.
- **N2:** a use on "X containing Y" measures Y (`resolve(…, contents=True)`). No gold path spells
  it so (0 of 1,282), but an agent may.
- **N3:** `measured/2` lasts one beat (above). It is not in the reading, so the per-reading atom
  counts in the table are 0.6 lower than at the step's first run.

## §2 The hand hierarchy for conductivity (world-scienceworld step 2, 2026-10-23): the formalization target

Five lifted specialists (`domains/hier/*_domain.llp`), instances generated per activation
(`world/gen_hier.py`), the manual switch (`experiments/hier.py`): the task domain plans — goto(R)
to nav, get(O) to grasp, test(O) to the circuit, put(O, Box) to the verdict — and the specialists
act. Nothing of the simulator's hidden properties is read: the answer is the bulb. **Every action
waits for the world's answer** (v2, opus's review N1): a rule sends a command and a second rule
consumes the world's own line for it — said(moved), said(picked), said(focused), said(connected),
said(waited), said(moved_obj), said(looked) — with the next beat's sync, before the chain goes on
or a result goes out. A result is never the rule's word.

| split | n | won | activations per variation | commands per variation | refused | s per variation |
|---|---|---|---|---|---|---|
| train (discovery) | 20 | 20 | 4 | 14.7 | 0 | 29.0 |
| test (held out) | 10 | 10 | 4 | 14.8 | 0 | 27.4 |

**The vector** (rules / predicates per specialist's base): nav 8/11, grasp 4/11, circuit 21/34, verdict 2/4, task 8/17.
The gating doubles the acting rules (v1 had nav 4, grasp 3, circuit 12, verdict 1): each action is
two rules, the sending and the hearing. That is the honest price of a rule that never claims what
the world has not said; the loop's refactor will meet the same shape (a send/hear pair is one
"action with its answer" to lift).

**What the hierarchy knows that the loop must find** (instance knowledge, declared in gen_hier.py):
the HOUSE graph and its routes (one constant per family, walked once with the gym; nav's `next/3`);
the circuit's parts — a wire has two terminals, a battery and a bulb have an anode and a cathode,
the thing under test has two terminals (the referents the game accepts); where the task's text
puts the thing (`where/2`, read by the perceiver). The one CAUSAL rule, nowhere in the text: a
thing wired in series with a battery and a bulb CONDUCTS iff the bulb is lit after a wait
(`circuit_domain.llp` `lit`/`dark`).

**Findings while writing the rules:**
- **The verdict must wait for the world.** A chain of acting rules runs inside one kernel beat;
  the host sends each command as its rule fires, but the perception is synced only at the next
  tick. A `lit`/`dark` rule reading `state(bulb, …)` right after `look` reads the bulb as it was
  before the wiring and answers wrong (the first run: 14/20, every loss a wrong box). Hence the
  send/hear pairs above, for every action.
- **Wire a bulb whose state the room shows.** Some variations have a plain "light bulb" beside
  the coloured ones, with no state in the text; a circuit through it never answers (the second
  run: 6 silent variations). `connect_3` picks a bulb with `state(L, off)`.
- **The ending step's events must reach the program.** The move into the box ends the episode;
  a host that answers `None` at once loses the move's line, and `placed` never fires. The host
  gives one last beat after the end.
- **"(disconnecting X)You move …"** hid the move's event behind a parenthesis; the perceiver
  strips it.

Baseline against it: §1's gold paths (the simulator's own solution) use 15–43 steps; the
hierarchy's 13–16 commands win the same variations. The empty-domain loop (step 3) must reach this
table: 20/20 and 10/10, with this vector or less, and say what it cost.

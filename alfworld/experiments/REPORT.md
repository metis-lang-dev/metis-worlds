# world-alfworld — step 1 report (the architect, 2026-10-21)

## What is built
The world repository runs ALFWorld's text games under a catalog host with the kernel's
program acting (README: the layout, the findings). A game becomes a PACKAGE
(`world/gen_instance.py`): its types, static facts and task over the lifted base
`domains/alfred_domain.llp` (ALFRED's actions as the agent's beliefs, a greedy
pick-and-place policy, 11 rules). The host (`world/alf_host.py`) turns a fired rule into
the game's command, reads the facts back, syncs the program, replays for restore and
logs every command with the game's verdict. Seven tests (`tests/`), green; the package's
case runs identically in metisc and metispy.

## The baseline (no loop): the faithful beliefs
`experiments/baseline.py`, the first family (`pick_and_place_simple`), seed 1:

| split | games | won | commands per game | refused |
|---|---|---|---|---|
| train (discovery) | 10 | **10** | 4–5 | 0 |
| valid_unseen (held-out scenes) | 10 | **10** | 4–6 | 0 |

A first run won 9/10: with several receptacles of the destination type (four drawers) the
greedy policy wandered between them (29 commands) because "open this one" and "go to
another" were both enabled; the base gained `arrived(R)` / `seeking` (one destination once
reached) and the loss went away. Records: `experiments/records/baseline-*.json`.

**Reading.** With the PDDL's own preconditions as beliefs, the world never refuses and the
task is won: this is the CONTROL. Learning needs beliefs with gaps — the learning runs
(step 3) start from ABLATED bases and the loop must recover each gap from the refusals:

| ablation | what the beliefs lack | what the world does | what the loop must learn |
|---|---|---|---|
| `no-open` | the open rules and the openable guards on take/put | a take from a closed fridge / a put into a closed cabinet: "Nothing happens." (the facts stay; the rule said it happened) | "a closed receptacle must be opened first" — one rule and two guards |
| `no-type` | `dest(R)` resolved to any receptacle (no parent type) | a put where the task wants another receptacle: the game accepts the move but never wins | the task's type condition (a goal, not a precondition: the signal is "no win", the records show where it put things) |
| `no-contain` | `cancontain` ignored (a later family: movable receptacles) | the put refused | the containment table |
| `no-hands` | `handsfree` ignored on take | a second take while holding: refused | "one thing in hand" |

Each ablation is a flag of the generator (what it leaves out of the instance) or a variant
of the base (what rules it omits), so the learning run's starting point is reproducible
and the recovered rule can be compared with the faithful one, token for token.

## The complexity vector (first family, 3 games, 15-step random walks)
`experiments/records/complexity-train-pick_and_place_simple.json`: ~190 facts per state
(~50 dynamic); 13 distinct states per 15-step walk; action branching mean 19, p95 26
(admissible commands per state); outcome branching 1 and conditional entropy 0 (the text
game is deterministic: every surprise is a missing rule, the reading the research note asks
for); horizon 5–7 (the greedy plan); 11 base rules; distribution: train 790 / valid_seen 35
/ valid_unseen 24 games of this family (the seven families: 3,553 train games); partial
observability 0.94 — the text names 6% of the placement and open facts, the host reads them
all (a later experiment can give the program only what the text names).

## Findings for the metis side (step 2)
1. The host's command log (`$METIS_ALF_LOG`) is the surprise record's raw material: the
   rule, the command, admissible or not, what changed, what the game offered instead. The
   domain agent's own record (the watch's surprise) is the one the loop should read; the
   log is the cross-check.
2. The REPL's `run N` fires every enabled rule before the first tick (all six commands in
   beat 0); the domain agent's clock (one beat, one pass) is the shape the learning runs
   need, so the closure drives the domain agent, not the REPL.
3. A refused command leaves the program's effect in place until the next sync retracts it:
   the watch sees the disagreement at the beat's end — that is the surprise. For a put
   that the game accepts but that does not win (the `no-type` ablation), the signal is the
   episode's outcome, not a surprise: the gate policy must read both.
4. `world(lines)` is unsupported (the game is the world); a scenario is another game.
5. The rule count regex in `complexity.py` counts `[dyn]` rules: 11 after `arrived`.

## The hierarchy by hand (alf-hierarchy s-ee212820 step 1, 2026-10-22; docs/HIERARCHY.md)

The same family through five lifted specialists (`domains/hier/`: nav, access, grasp, place,
task) with a MANUAL switch (`experiments/hier.py`): one kernel run per activation, the
driver's table `{goto: nav, open: access, take: grasp, put: place}` is the switch, the task
domain emits one sub-goal at a time and gets the result atom back. The same 20 games as the
baseline (seed 1):

| games | won | refusals | activations / game | commands / game | seconds / game |
|---|---|---|---|---|---|
| train (discovery) | 10/10 | 0 | 6.0 | 4.4 | 18 |
| valid_unseen (held out) | 10/10 | 0 | 6.0 | 4.9 | 20 |

Every game: six activations (nav, access, grasp, nav, access, place), 4–5 commands (the
flat program's 4–5: `access` sends no command when the receptacle has nothing to open), no
refusal, the same win. Both records were taken with `fetch(O, R)` as the task's one way in
(9b3f600): the driver seeds the first target and the first destination, the same atom the
FETCH intent types.

**The complexity vector per domain** (`experiments/hier_vector.py`, one game, the
activation instances along the task's plan; the ground bound = Σ over the declared
predicates of the product of their argument types' sizes):

| domain | rules | preds | types (sizes) | static facts | #init | ground atoms (bound) |
|---|---|---|---|---|---|---|
| flat | 10 | 43 | location 18, receptacle 12, object 24, otype 15, rtype 8 | 122 | 47 | 1903 |
| nav | 2 | 4 | location 18, receptacle 12 | 12 | 2 | 42 |
| access | 4 | 10 | location 18, receptacle 12 | 24 | 6 | 90 |
| grasp | 5 | 14 | location 18, receptacle 12, object 1 | 24 | 9 | 78 |
| place | 5 | 14 | location 18, receptacle 12, object 1 | 24 | 9 | 111 |
| task | 11 | 21 | object 2, receptacle 12, thing 14 | 14 | 3 | 206 |
| specialists, sum | 27 | 63 | | 98 | 29 | 527 |
| specialists, max | 11 | 21 | | 24 | 9 | 206 |

What the split buys: no activation grounds more than 206 atoms against the flat program's
1 903 (9×), and the specialists summed stay at 527 (3.6×) — because each activation's
instance is NARROWED to the things its goal names (grasp and place see one object, the
task its targets; `gen_hier.py`, the host's `things` filter), which the flat program cannot
do (it chooses among all objects itself). nav is 2 rules over 42 atoms; access 4 over 90.
The task domain is the largest (11 rules, 206 atoms) because `thing` (objects ∪
receptacles) types the refusals — the price of `stuck(X)` being one predicate.

Findings for steps 2–3: (1) a result atom per outcome and a refusal per dead end made the
driver trivial — the switch is the host reading `out`; the director (step 3) replaces the
table with `handles/2` over the same atoms; (2) the task domain never needs to know
whether a receptacle opens — asking `access` always is simpler and costs no command;
(3) `thing`-typed refusals force a second end (`wrong_dest`) because a variable is typed
once per rule — a lifted base wanting one `stuck` over mixed kinds needs a union type the
instance declares, which gen_hier does; (4) the replay of the commands so far
(`game.json: replay`) makes every activation a fresh process over the same game state —
60 s per game at worst, fine for the text game, not for a simulator with a slow reset
(MiniHack's host should keep the process and switch packages in it).

## The director makes the switch (alf-hierarchy step 3, 2026-10-22; docs/HIERARCHY.md §Step 3)

The same 20 games with `experiments/hier.py --director`: the table is gone, the director's
rules (`domains/director_domain.llp`, its instance generated from the specialists' declared
ports) wake, route and sleep the specialists from the kinds that arrive:

| games | won | refusals | activations / game | director beats / game | seconds / game |
|---|---|---|---|---|---|
| train | 10/10 | 0 | 6.0 | 20.0 | 68 |
| valid_unseen | 10/10 | 0 | 6.0 | 20.0 | 69 |

The same six activations and the same commands as the manual switch; 20 beats per game
(the seed, then goal / result / idle per activation, the end); the time is the kernel runs
(one per beat, a fresh process each — the agent keeps the director in memory and pays none
of it). The detour a person makes and the task never does — `open(R)` from elsewhere →
`elsewhere(R)` → nav → `reached(R)` → the goal back → `accessible(R)` — is a test, not a
run: no game in the family produces it. Activation needs no model: the rules did every
switch; the small model's part is typing the person's words into the attended card, two
cards served instead of five.

## Next
world-alfworld step 2 is REPLACED by loop-policy (s-dd842f2a, metis-agentic-loop
docs/POLICY.md): the loop builds this family from an EMPTY domain in phases (exploration /
exploitation / refactoring) with disengagement, and is compared to the flat program above
and the hierarchy by hand. alf-hierarchy step 2 (opus): an intent card per specialist on
E2B and the agent over a specialist package; step 3: the director instance activating the
specialists from the task's sub-goals and from the world's facts.

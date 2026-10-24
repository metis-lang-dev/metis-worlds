# ALFWorld as a hierarchy of domains (alf-hierarchy, the architect, 2026-10-22)

The user: "split ALFWorld into hierarchical domains to reduce complexity — first with a
manual switch and domain activation; add an LLM agent and intents per domain; add an
orchestrator domain and find the way to activate domains automatically."

## Why split

The flat `alfred_domain.llp` (step 1) holds the whole household in one program: 11 rules,
31 predicates, every static fact of the game (~500) and every dynamic fact (~30) in one
grounding, and one policy token set (`want`, `carrying`, `arrived`, `seeking`) threaded
through all of it. It wins 20/20, and it is the wrong shape for learning: a rule the loop
proposes about opening a fridge is grounded against tomatoes and countertops; the surprise
"the drawer would not open" lands in a program where going, taking and putting share the
state; and a person's "open the fridge" has no domain of its own to be typed into.

A hierarchy puts each activity in a domain that sees only what the activity needs. The
complexity vector (LEARNING.md) is measured PER DOMAIN, and the claim is that every
specialist's vector is a fraction of the flat one while the task still wins.

## The specialists (`domains/hier/*_domain.llp`, lifted; instances generated per game)

| domain | goal in (its port) | result out | world facts it sees | rules |
|---|---|---|---|---|
| `nav` | `goto(R)` | `reached(R)` | `at(L)`; `recat(R, L)` | go, here |
| `access` | `open(R)` | `accessible(R)` / `refused(R)` | `at`, `opened`, `closed`; `recat`, `openable`, `notopenable` | open_closed, already_open, no_door, not_here |
| `grasp` | `take(O)` | `taken(O)` / `refused(O)` | `at`, `objat`, `inrecep`, `opened`, `closed`, `holds`, `holding`, `handsfree`; `recat`, `openable`, `notopenable` | take_open, take_plain, not_here, shut, hands_full |
| `place` | `put(O, R)` | `placed(O, R)` / `refused(R)` | `at`, `opened`, `closed`, `holds`, `holding`, `handsfree`; `recat`, `openable`, `notopenable` | put_open, put_plain, not_here, shut, empty_handed |
| `task` | `fetch(O, R)` — the one way in: the FETCH intent a person types, or the driver's seed (first target, first destination); the task's facts `target(O)`, `dest(R)`, `notdest(R)`; the results above | `goto`, `open`, `take`, `put` (the sub-goals), `done`, `stuck(X)`, `wrong_dest(R)` | `inrecep(O, R)` | fetch, not_dest, go_for, open_for, take_for, go_dest, open_dest, put_dest, finish, stuck_fetch, stuck_carry |

Conventions, the same as console-nav's ui base:
- a goal atom is consumed by exactly one rule per state (the explorer's check), and every
  non-acting outcome has a `%%` line — `already_open` ("{R} is already open"), `no_door`
  ("{R} has nothing to open"), `not_here` ("I am not at {R}") are rules, not silences;
- a REFUSAL is a result (`refused(R)` with its reason line), never a stall: the task's
  `stuck(X)` rule turns it into the episode's end, and in task 2's policy that is the
  disengagement point;
- the acting rules keep the names the host's command table knows (`go`, `open_closed`,
  `take_open`/`take_plain`, `put_open`/`put_plain`); the rest send no command;
- LL has no negation: the instance supplies `closed(R)`, `notopenable(R)`, `handsfree`.

The task domain is the planner: it emits one sub-goal at a time and waits for the result
atom; it never acts in the world itself. Its policy is the flat domain's greedy one,
re-stated as sub-goals: fetch the target where it is (go, open, take), carry it to the
destination (go, open, put). It does not know whether a receptacle is openable — it always
asks `access`, which answers at once when there is nothing to open. That is the point of
the split: the task knows WHAT, the specialists know HOW.

## Step 1 — the manual switch (the architect; this step)

`experiments/hier.py` runs one game as a sequence of kernel runs, one per activation:

1. the `task` instance runs until a sub-goal atom appears (the host sees it in the
   counts and ends the episode: tick → None);
2. the driver activates the specialist that HANDLES that atom — a table in the driver,
   `{goto: nav, open: access, take: grasp, put: place}`, written by hand (this is the
   manual switch);
3. the specialist's instance is generated with the game's CURRENT facts (the driver mirrors
   every command onto its own copy of the game; the specialist's host replays the same
   commands, `game.json: replay`) and the sub-goal as its `#init`; it runs until a result
   atom appears;
4. the result goes into the task's next `#init` with the task's own tokens carried over
   (the host logs the program's own tokens at each tick); back to 1 until `done` or
   `stuck`.

What is measured: per game the activations, the commands, the win; per domain the vector
(rules, predicates, declared types' sizes, `#init` facts) against the flat domain's. The
record: `experiments/records/hier-<split>-<task>-<seed>.json`, the report in
`experiments/REPORT.md` §hierarchy.

## Step 2 — the agent and the intents per domain (opus, nina)

Each specialist gets an `intent.yaml` (nav: GO(receptacle); access: OPEN(receptacle);
grasp: TAKE(object); place: PUT(object, receptacle); task: FETCH(object, receptacle) over
the game's words) and a card checked on Gemma E2B with `metis_agent.intent_check` per
domain AND on the union — the union's miss rate is the number the director then removes
(it serves two cards, not five). The domain agent (metis-agent) over a specialist package
runs the kernel as the flat one did, with the person's words typed into the ATTENDED
specialist's card. Nothing of the flat domain changes; the hierarchy is a second tree under
`domains/hier/`.

## Step 3 — the orchestrator domain: the director (the architect: the base and the instance,
done; opus: the orchestrator; nina: the generator)

Activation is RULES, not a model. `domains/director_domain.llp` is the lifted director of
metis-agent `docs/DIRECTOR.md`: it sees KINDS — `seen(K)`, an atom of kind K arrived; the
atom's arguments ride in the orchestrator's frame, not in the director — and a specialist's
idleness, `idle(D)`; its effects are the agent's own verbs, `wake(D)`, `sleep(D)`,
`forward(D, K)`, `ask(K)`, `ended(K)`. The ALFWorld instance (`gen_hier.generate_director`)
is GENERATED from the specialists' declared ports (`SPECS`: a goal kind in, result kinds
out — decision 1, the SDK generator's job later): `handles(nav, goto)`, `handles(access,
open)`, …, `handles(task, fetch | reached | accessible | taken | placed | refused)`,
`planner(task)`, `result/1`, `end/1`, `detour(elsewhere, goto)`, `escalate(elsewhere,
refused)`. One beat = one arrival; the driver (`experiments/hier.py --director`) runs the
director, reads its effects, and acts on them — the table of step 1 is gone.

The rules: `wake_for` (a kind a sleeping specialist handles wakes it and gets the goal),
`route` (a kind the planner handles goes to it; `attention` follows), `route_busy`,
`sleep` (a specialist is idle after its result: linger 1 beat, decision 3), `detour` (a
specialist answers `elsewhere(R)`: its goal is put aside as `pending`, the navigator is
woken with `goto`, once), `resume` (the navigator's result wakes the specialist with its
pending goal), `escalate` (a second `elsewhere` while a detour is open becomes `refused` for
the planner), `ended`/`unknown` (an end kind or a kind nobody handles → `ask`: the
disengagement hook of loop-policy). The specialists' "I am not there" refusals are the
kind `elsewhere(R)` for that reason; shut / hands-full / empty-handed stay `refused`.

Measured: the same 20 games through the director (records `hier-director-*`) — the same
six activations per game, 20 director beats each (goal, result, idle per activation, the
seed and the end), won; and the detour scenario a person makes and the task never does:
`open(cabinet1)` typed while the agent stands elsewhere → access answers
`elsewhere(cabinet1)` → the director sleeps access, wakes nav with `goto(cabinet1)` →
`reached` → access gets `open(cabinet1)` back → `accessible(cabinet1)`, routed to the task
(two tests in `tests/test_world.py`). Attention = the last routed domain (decision 2).

What remains of step 3 on the agent side (opus, with nina's generator): the orchestrator
runs this director's package beside the attended specialist's only (decision 4; opus's F3:
a deactivated card leaves the turn), the specialists stay installed and are re-instanced per
activation so a result is voiced as the result and not as the end of a run (F4, F5), and
the frames are the orchestrator's (the atom behind a kind, kept through a detour). The
world-driven source of activation (a world fact alone waking a specialist, HIERARCHY v1's
second source) needs reactive specialists — the flat rules partitioned by activity, no
planner — and is a later measurement, not this step's.

### Step 3, measured in the agent (opus, metis-agent main 9021409; the architect's note, 2026-10-22)

The director runs inside metis-agent: a game is installed (`gen_hier.install(game_dir, root)`:
the director package with its host, the task's person-mode instance, an empty instance per
specialist, a shared commands log every host replays), then only the person's words — "bring
the X to the Y" — and the rules make every switch.

| games through the agent | won | director beats | activations | commands per game |
|---|---|---|---|---|
| train | 10/10 | 19 | 6 | 4.4 |
| valid_unseen | 10/10 | 19 | 6 | 4.6 |

The same specialist goals and command counts as `hier.py --director`, game for game. The model's
turn holds the director's card and the attended card only (F3, `v3.serve: active`): ~3.9k tokens,
not growing (step 2's union reached 15,360 and overflowed at the twelfth activation).

**The measured answer to F3.** On nina's relabeled corpus the UNION of every specialist's card
scores 132/143 = **0.923**; ATTENDED — each row meets its own card alone in the orchestrator's
turn and grammar — scores 142/143 = **0.993**. The routing the small model cannot do (E12) is the
director's rules; the model only types the person's words into the one card that is up.

What the wire needed from the world, found in the run and fixed (opus's W1–W7): a shim named
like the world module imported itself (metis.host.world_host puts the world directory first;
the agent keys its shims apart); a won game under `continues` is not the run's end (the planner
puts out `done`, the director ends the run); re-instancing takes a domain's HELD tokens only, not
the world's facts or its results (`director_host.own_tokens`); an installed task seeds no fetch
(`install(person=True)`): the person's FETCH is its goal. Step 4 is the user's gate.

## Roles, not rooms (semantic-map s-d4270bed step 2)

The room left the source. Each specialist is compiled ONCE: `domains/hier/<spec>/<spec>.llp` is
its base plus `domains/hier/capacity.llp`, the role vocabulary (`gen_hier.capacity(k)`, k = 8
committed):

- `object {target other}`;
- `receptacle {dest p0 p1..pk}`;
- `location {lhere ldest l1..lk}`.

The task's statics hold in every room (`target(target). dest(dest). nottarget(other).
notdest(p0..pk).`). The room lives in the host: `semantic_map.SemanticMap`, one
`domains/hier/.map.json` beside the commands log. It holds the places, the things, the agent,
the task, and a belief per thing.

**The projection.** Per goal, `project(obj, rec)` binds the roles to the map's entries:
- `target`: the goal's object, when the task wants it;
- `other`: a named object it does not want;
- `dest`: the goal's receptacle, when it is a dest;
- `p0`: the receptacle where the robot stands;
- `p1..pk`: a named non-dest receptacle, then the places by belief of holding the target;
- the location roles follow their places, and a shared location keeps one role.

**What follows from it:**
- **The reading.** The hosts read the world through the binding (`role_reading`, with
  recat/openable/notopenable now dynamic facts the projection asserts).
- **Rebinding.** A rebinding is the host's sync, retract and assert on the live session, so
  nothing is recompiled.
- **Delivery.** `director_host.deliver()` gives every domain its next activation as do-lines;
  `instance()` only re-projects for a reload (a new game).
- **The room's terms.** The person's FETCH arrives in the room's terms (the card is built from
  the map); `AlfHost.intent_atom` projects it.
- **The voice.** The commands, the voice (`speak`), the goal text and the chain (`in_room`) say
  the bound things; `ports()` carries `name(role, thing)`.
- **Belief.** The task's `go_for` is weighted by `look(O, R)`, the map's normalized belief.

Grounding (CPU, `test_the_capacity_grounds_small`):

| specialist | k = 4 | k = 8 (committed) | k = 16 |
|---|---|---|---|
| nav | 216 events, 1 ms | 1,000, 3 ms | 5,832, 18 ms |
| access | 288, 2 ms | 1,200, 4 ms | 6,480, 18 ms |
| grasp / place | 588, 3 ms | 2,420, 9 ms | 12,996, 42 ms |
| task | 134, 2 ms | 218, 3 ms | 386, 3 ms |

The full room was 159k events for grasp/place, and today's narrowed instance about 3k, paid on
every activation. With roles, grounding is paid once, at load.

## What it gives the agent paper

The same family, three programs: flat (step 1 of world-alfworld), hierarchical by hand
(this subject), hierarchical by the loop (loop-policy's refactoring phase) — each with its
complexity vector and its held-out success. The reduction is the claim; the loop
reproducing the hand split is the result.

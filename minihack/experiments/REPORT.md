# world-minihack — step 1 report (the architect, 2026-10-22)

## What is built
The world repository runs MiniHack levels under a catalog host with the small LLM agent
meant to act (README: the layout, the findings). A level variant becomes a PACKAGE
(`world/gen_level.py`): the level's cells and names as types, the perceived start as
`#init`, the card (`world/card.yaml`: MOVE(dir), PICKUP, EAT, OPEN(dir), KICK(dir),
SEARCH, DOWN, WAIT, APPLY, UNKNOWN), the host shim — and NO rules: the domain is what the
agent's runs extract (LEARNING.md: agent first, domain after). The perception adapter
(`world/perceive.py`) reads NLE's screen into atoms over the level's own cells (objects and
monsters by name, doors, stairs, traps once seen, the status, the inventory) and types the
message line into events (`said(blocked)`, `said(see_here)`, `said(picked)`,
`said(killed)`, …). The host (`world/mh_host.py`) maps a fired rule by its name to an NLE
action, hands the message's events to the program for one beat, syncs, replays
deterministically (NLE's own seeding), and logs every action. Five tests, green; the
generated package compiles; the card passes the generator's check.

## The family and its splits
`world/levels.py`, the `room` family: 144 variants = 3 sizes × {no item, apple, key} ×
{no monster, newt, rat, jackal} × {no door, closed door} × {no trap, pit}, built with
MiniHack's LevelGenerator from a seed. **Discovery: 75 variants; held out: 69** — every
variant with BOTH a monster and a trap, or BOTH a door and a key: the compositions the
agent never sees while the rules are extracted, the test of compositional generalization
the research note asks for.

## The card on Gemma E2B
`metis_agent.intent_check --examples` (local, 0 USD): **16/16** examples typed right and
mapped. A corpus of held-out paraphrases is step 2's, once the agent runs.

## Findings for the metis side (step 2)
1. **The extraction's naming convention.** The host maps a fired rule by its name: a rule
   consuming `cmd_X(...)` must be named `X` or `X_<why>` (as the alfred base's
   `take_open`/`take_plain`). The agentic loop's extraction must keep that convention, or
   the extracted program moves nothing.
2. **The program before extraction has no rules but `unknown`.** The domain agent serves it
   (the card maps, the host acts on the fired `unknown`? no: `unknown` is refused); so the
   agent-in-the-loop needs a different first mode: the typed intent's command goes to the
   host DIRECTLY (a `cmd_*` the program holds is handed to the host as the action) until a
   rule for it exists — the extraction then writes the rule from the records of what the
   command did. That is the one metis-side mechanism this world needs that ALFWorld did
   not: "act without a rule, record, then write the rule".
3. **Events ride one beat.** `said(KIND)` atoms are handed in with the next tick and taken
   off at the one after; a rule that reads them must read them in that beat.
4. **The episode ends on the stairs** (the terminal reward is the win); the host answers
   nothing after `done`. A level without stairs never ends: `max_steps` bounds it.
5. **Every variant is a package** (cells and names differ): the extraction should write one
   LIFTED base per family and let the generator produce the instance, as alfred does — the
   lifting is the generalization: a rule about "a closed door" written once must hold on
   every variant that has one.

## Next
Step 2 (opus, nina): the agent in the loop — metis-agent serving a package with the E2B
agent acting from the card, the "act without a rule" mode, the records, the extraction
(`take` + formalize over the records as prose) into a lifted base for the family, the
experimental gate on the held-out variants, the metrics. Step 3 (the architect): the
measured runs and the comparison with ALFWorld's approach for the agent paper.



## §2a — the small agent in the level (nina, 2026-10-22; world-minihack step 2a)

Gemma E2B (local, 0 USD) acting from the card through metis-agent's domain agent: **act without a rule**.
- **The manifest key:** `actor: {max_steps: 40, task: …}`.
- **The act:** the host's `act(atom)` runs a command no rule took.
- **What the model is given:** the host's `describe()` of its perception atoms, the task line, and the last action with whether the world took it. Never the des, never the screen.
- **The runs:** the discovery split, all 75 variants, each once (seed 1), unattended, with a 40-step cap (`experiments/agent_run.py run`).

### Three task lines (the baseline is the third)

This family wins on ARRIVAL: stepping onto the stairs ends the episode won, and DOWN can never be right (opus's review R1). The card is a person's card, and it maps any "stairs" to DOWN: its own examples are "go down the stairs" and "descend", and "down" means south "unless the stairs are meant". So the words decide the baseline:

| task line (the reading calls the stairs) | won | ends | mean steps | refusals / episode | intents | door=closed won | journals |
|---|---|---|---|---|---|---|---|
| "find the stairs down and go down them" ("the stairs down") | 10 | cap 57, done 8, won 10 | 32.8 | 27.2 | DOWN 82%, SEARCH 15%, MOVE 3% | 0/30 | `records/agent-2a-s1/` |
| "walk onto the stairs: standing on them wins" ("the stairs down") | 0 | cap 75 | 40.0 | 37.9 | DOWN 92%, MOVE 8% | 0/30 | `records/agent-2a-s1-stairs/` |
| **"walk onto the goal: standing on it wins"** ("the goal (a staircase)") | 51 | cap 21, done 3, won 51 | 14.8 | 10.0 | MOVE 80%, SEARCH 13%, OPEN 7% | 7/30 | `records/agent-2a-s1-goal/` |

- **"Go down them":** DOWN 82%. The 10 wins were MOVEs that happened to step onto the stairs.
- **"Walk onto the stairs":** DOWN 92%, 0 wins. The word "stairs" alone is enough.
- **The goal (the third):** the reading names the stairs down "the goal (a staircase)", and the up stairs "a staircase up (not the goal)". The task line carries no more than before: the family's goal is the stairs.
- **Probes before the reruns** (3 readings × 4 wordings): only the goal wording moved MOVE toward the stairs in every reading. "2 south of you" became DOWN with "stairs" and "staircase" in it.

### The baseline (the goal)

| measure | value |
|---|---|
| episodes | 75 |
| won | **51** (68%) |
| ends | cap 21, done 3, won 51 |
| mean steps | 14.8 |
| refusals per episode | 10.0 (the world did not take the command: nothing in the perception changed, and no fight) |
| intents typed | MOVE 886, SEARCH 139, OPEN 82 |
| cost | 0 |

**Win rate per feature** (won / episodes):

| feature | values |
|---|---|
| size | large 22/25 · medium 15/25 · small 14/25 |
| item | apple 18/30 · key 15/15 · none 18/30 |
| monster | jackal 11/15 · newt 11/15 · none 18/30 · rat 11/15 |
| door | closed 7/30 · none 44/45 |
| trap | none 42/60 · pit 9/15 |

**The kinds of surprise** (`agent_run.py report`, one record per kind and episode: what step 2b's extraction must turn into rules):

| kind | episodes | what it is | first |
|---|---|---|---|
| `walks_into_a_monster` | 14 | a move, then the world says it hit, or was hurt (a fight: taken, not refused) | room_large_apple_jackal_closed_none, step 4 |
| `repeats_a_refused_command` | 21 | the same command refused three times in a row (a move into a wall, a pickup with nothing here) | room_large_apple_none_closed_none, step 10 |
| `never_opens_the_door` | 20 | a door variant lost with no OPEN / KICK / APPLY typed at all | room_large_apple_none_closed_pit, step 1 |
| `never_picks_up_the_key` | 15 | a key variant with the key never held (discovery's key rooms have no door: the key is never needed) | room_large_key_jackal_none_none, step None |
| `killed_while_a_monster_bites` | 3 | the world ends the episode, the hp falling while a monster is in sight; the agent neither moves away nor fights | room_medium_apple_jackal_closed_none, step 13 |
| `falls_into_the_pit` | 2 | a move into the pit (said(fell_pit)) | room_medium_key_none_none_pit, step 2 |

**One named surprise per failing feature value** (13 of 13; the feature's own kind where an episode shows it):

- `size=large`: `repeats_a_refused_command` in room_large_apple_none_closed_none, step 10
- `size=medium`: `killed_while_a_monster_bites` in room_medium_apple_jackal_closed_none, step 13
- `size=small`: `repeats_a_refused_command` in room_small_apple_jackal_closed_none, step 3
- `item=apple`: `repeats_a_refused_command` in room_large_apple_none_closed_none, step 10
- `item=none`: `repeats_a_refused_command` in room_large_none_none_closed_pit, step 9
- `monster=jackal`: `killed_while_a_monster_bites` in room_medium_apple_jackal_closed_none, step 13
- `monster=newt`: `killed_while_a_monster_bites` in room_medium_apple_newt_closed_none, step 33
- `monster=none`: `repeats_a_refused_command` in room_large_apple_none_closed_none, step 10
- `monster=rat`: `killed_while_a_monster_bites` in room_medium_apple_rat_closed_none, step 12
- `door=closed`: `never_opens_the_door` in room_large_apple_none_closed_pit, step 1
- `door=none`: `repeats_a_refused_command` in room_small_none_none_none_none, step 4
- `trap=none`: `repeats_a_refused_command` in room_large_apple_none_closed_none, step 10
- `trap=pit`: `never_opens_the_door` in room_large_apple_none_closed_pit, step 1

**Reading.**
- **With words that don't pull toward DOWN, the small model walks.** The open rooms are almost all won (door=none 44/45).
- **The door is the barrier.** door=closed was won 7/30: OPEN was typed 82 times, but the stairs behind the wall are out of sight. `never_opens_the_door` is 20 episodes, and `never_sees_the_stairs` follows from it.
- **Monsters hurt more than they kill:** `walks_into_a_monster` in 14 episodes (fights, now counted as taken) and 3 deaths. The pit took 2.
- **Where these sit in the loop's policy** (metis-agentic-loop docs/POLICY.md):
  - The deaths (searching while bitten) are the **exploitation phase's surprise kind**.
  - `never_opens_the_door` is the one the **held-out door+key family** will measure: discovery has no locked door, so it tests a new skill from known parts (N1's ruling).
- This table is **the baseline the loop must beat**: step 2b's extracted rules are measured against it, on the held-out split (step 3).

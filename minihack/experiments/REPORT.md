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
- **The manifest key:** `actor: {max_steps: 40, task: "find the stairs down and go down them"}`.
- **The act:** the host's `act(atom)` runs a command no rule took.
- **What the model is given:** the host's `describe()` of its perception atoms, the task line, and the last action with whether the world took it. Never the des, never the screen.
- **The run:** the discovery split, all 75 variants, each once (seed 1), unattended, with a 40-step cap: `experiments/agent_run.py run`, 648 s.
- **The journals:** `experiments/records/agent-2a-s1/` (gitignored), one plain JSONL per episode (README, "The journals").

| measure | value |
|---|---|
| episodes | 75 |
| won | **10** (13%) |
| ends | cap 57, done 8, won 10 |
| mean steps | 32.8 |
| refusals per episode | 27.2 (the world did not take the command: nothing in the perception changed) |
| intents typed | DOWN 2023, SEARCH 364, MOVE 71 |
| cost | 0 |

**Win rate per feature** (won / episodes):

| feature | values |
|---|---|
| size | large 2/25 · medium 4/25 · small 4/25 |
| item | apple 6/30 · key 2/15 · none 2/30 |
| monster | jackal 1/15 · newt 1/15 · none 6/30 · rat 2/15 |
| door | closed 0/30 · none 10/45 |
| trap | none 8/60 · pit 2/15 |

**The kinds of surprise** (`agent_run.py report`, one record per kind and episode: what step 2b's extraction must turn into rules):

| kind | episodes | what it is | first |
|---|---|---|---|
| `repeats_a_refused_command` | 50 | the same command, refused three times in a row (DOWN off the stairs, a move into a wall) | room_large_apple_jackal_closed_none, step 3 |
| `never_opens_the_door` | 30 | a door variant lost with no OPEN / KICK / APPLY typed at all | room_large_apple_jackal_closed_none, step 1 |
| `walks_into_a_monster` | 4 | a move after which the world says it hit, or was hurt | room_large_apple_newt_closed_none, step 15 |
| `killed_while_a_monster_bites` | 8 | the world ends the episode, the hp falling while a monster is in sight; the agent neither moves away nor fights | room_large_apple_newt_closed_none, step 26 |
| `never_picks_up_the_key` | 15 | a key variant with the key never held | room_large_key_jackal_none_none, step None |
| `falls_into_the_pit` | 1 | a move into the pit (said(fell_pit)) | room_medium_key_none_none_pit, step 4 |

**One named surprise per failing feature value** (14 of 14; the feature's own kind where an episode shows it):

- `size=large`: `repeats_a_refused_command` in room_large_apple_jackal_closed_none, step 3
- `size=medium`: `killed_while_a_monster_bites` in room_medium_apple_jackal_closed_none, step 13
- `size=small`: `repeats_a_refused_command` in room_small_apple_jackal_closed_none, step 3
- `item=apple`: `repeats_a_refused_command` in room_large_apple_jackal_closed_none, step 3
- `item=key`: `never_picks_up_the_key` in room_large_key_jackal_none_none, step None
- `item=none`: `killed_while_a_monster_bites` in room_large_none_jackal_closed_none, step 12
- `monster=jackal`: `killed_while_a_monster_bites` in room_large_none_jackal_closed_none, step 12
- `monster=newt`: `walks_into_a_monster` in room_large_apple_newt_closed_none, step 15
- `monster=none`: `never_opens_the_door` in room_large_apple_none_closed_none, step 1
- `monster=rat`: `killed_while_a_monster_bites` in room_large_apple_rat_closed_none, step 12
- `door=closed`: `never_opens_the_door` in room_large_apple_jackal_closed_none, step 1
- `door=none`: `repeats_a_refused_command` in room_large_apple_jackal_none_none, step 5
- `trap=none`: `repeats_a_refused_command` in room_large_apple_jackal_closed_none, step 3
- `trap=pit`: `falls_into_the_pit` in room_medium_key_none_none_pit, step 4

**Reading.**
- **The card is a person's card, and E2B answers it like one.** DOWN is 82% of all intents: with no rule, the model reads "go down them" in the task and "the stairs down" in the reading as the verb.
  - A framing probe before the run (3 readings × 3 framings) moved MOVE toward visible stairs, and DOWN onto them, only when the reading came first and the question was "what one action do you take now, from where you stand?" (the actor's framing).
  - Even so, the agent typed DOWN one cell short of the stairs and repeated it: `repeats_a_refused_command` in 50 of 75. That's the first rule the extraction owes: DOWN is refused unless the stairs are here.
- **The door is never touched.** 0 of 30 door variants were won, and no OPEN, KICK or APPLY was typed in any of them. Behind the wall the stairs are out of sight, so the reading never motivates the door: `never_opens_the_door`.
- **Monsters kill a searching agent.** All 8 episodes the world ended were deaths: SEARCH typed while a newt, rat or jackal bit (hp falling). It's a rule about attack or flight to extract.
- **The wins are the easy rooms:** no door, the stairs in sight, 2 to 4 moves.
- **Where these sit in the loop's policy** (metis-agentic-loop docs/POLICY.md):
  - The deaths (searching while bitten) are the **exploitation phase's surprise kind**: a world change the program's
    beliefs don't predict.
  - `never_opens_the_door` is the one the **held-out door+key family** will measure. Discovery has no locked door,
    so it tests a new skill built from known parts (the architect's N1 ruling).
- This table is **the baseline the loop must beat**: step 2b's extracted rules are measured against it, on the
  held-out split (step 3).

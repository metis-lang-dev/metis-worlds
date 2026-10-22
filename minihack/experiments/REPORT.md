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

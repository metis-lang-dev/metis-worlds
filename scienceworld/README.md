# scienceworld — the third learning world: a text laboratory with hidden properties (metis-worlds)

[ScienceWorld](https://github.com/allenai/ScienceWorld) (1.2.3; a Java simulator over py4j) under
the metis agentic loop. Its tasks hide the property they ask about — is the foil conductive, what
is substance C's melting point — and only an EXPERIMENT reveals it: wire the thing into a circuit
and look at the bulb; heat it and read the thermometer. That is the loop policy's exploration
phase (metis-loop pi/docs/POLICY.md) with a real causal rule to find. 30 task types, 30–900
variations each, split train / dev / test by the environment: the held-out measure for free.

**The honesty rule.** The agent perceives the TEXT only: the room description, the inventory,
the step's result. The simulator's object tree (every object with `electricallyConductive`,
`meltingPoint`, …) is the ORACLE: tests and measurements may read it (`sw_gym` op `oracle`), the
agent's input never. A package's `thing` type is the simulator's referent list (names only).

## Layout (step 1)

| path | what |
|---|---|
| `setup.sh` | the world's venv (`.venv/`, or `.worlds/sw` beside the checkouts: the host walks up to it); needs `java` |
| `world/sw_gym.py` | one task variation as a child process (JSON lines): open / reset / step / gold / oracle / close; an ambiguous referent is answered with its first reading |
| `world/perceive.py` | the text as atoms: `here(R)`, `door(R2, open\|closed)`, `in(O, C)` (the room, "On the table is: …", "(containing …)"), `state(O, on\|off)`, `closed(C)`/`open(C)`, `reads(O, nN)`, `holds(O)`; the result line as one beat of `said(KIND)` events; the task's words → `task(conductivity, target, box_if_yes, box_if_no)` |
| `world/sw_host.py` | the host: a fired `cmd_X[…]` → the game's verb; a command the game's `valid` list lacks is REFUSED (`said(cant)`, no step); `focused(O)` and `connected(A, B)` kept from the results (the look never says them; a move disconnects); snapshot/restore by replay; `$METIS_SW_LOG` |
| `world/families.py` | `conductivity` (test-conductivity, …-of-unknown-substances), `melting`; the env's train (discovery) / dev / test (held-out) variations |
| `world/gen_instance.py` + `world/card.yaml` | a variation as a PACKAGE `domains/<task>_<n>/`: declarations + the perceived start + the task, NO rules; the card: GO, OPEN, CLOSE, TAKE, DROP, FOCUS, CONNECT(a, b), MOVE(o, c), ACTIVATE, DEACTIVATE, WAIT, LOOK, UNKNOWN |
| `experiments/baseline.py` | the gold paths through the host, command by command: score 100 reproduced, the perception vector per step |
| `tests/` | the perceiver on fixed texts, the gold path winning through the host, a refusal and a restore, the package compiling |

```
METISC=../../metis-lang/src/metisc ../../.worlds/sw/bin/python -m pytest scienceworld/tests -q      # from the metis-worlds root
../.worlds/sw/bin/python scienceworld/experiments/baseline.py --family conductivity --n 20
```

## What the loop must discover (step 2's hand hierarchy says it; step 3's loop finds it)

`conducts(X)` is never in the text. The circuit — battery, two wires, a bulb, X between — lit
(`state(red_light_bulb, on)` after a `wait`) says yes; dark after the wait says no. Then the
verdict: `move X to <box_if_yes|box_if_no>`.

## Findings while building (step 1)

- **Rooms connect by doors, walked**: `go to R` works only through a door of the current room
  (the `easy` simplification opens doors and containers; `teleportAction` is a separate one, not
  used). A gold path can be a 14-step walk before the task's room.
- **An ambiguous referent is a question**: "pick up orange" with an orange in the bowl and one
  in the inventory makes the game ask which; the gym answers the first reading, so the host
  never hangs on a prompt. Qualified referents ("cup containing nothing in table") are what the
  `valid` list carries.
- **The look's grammar is small**: "a X. On the X is: a, b." · "a X (containing a, b)" · "a X. The
  X door is closed." · "a X, which is turned off" / "which is on" / "deactivated" · "a thermometer,
  currently reading a temperature of N degrees celsius" · "A door to the R (that is open)".
  A clause "which is off" after a comma belongs to the item before it.
- **28 ms per step** in the simulator; a variation's gold path of 17–30 steps runs in a second.

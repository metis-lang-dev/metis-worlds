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
| `world/perceive.py` | the text as atoms: `here(R)`, `door(R2, open\|closed)`, `in(O, C)` (the room, "On the table is: …", "(containing …)"), `state(O, on\|off)`, `closed(C)`/`open(C)`, `reads(O, nN)` (in the room or held), `holds(O)`, `matter(O, solid\|liquid\|gas)` (when the name says it); the result line as one beat of `said(KIND)` events; the task's words → `task(conductivity, target, box_if_yes, box_if_no)` or `task(melting, substance, box_if_above, box_if_below)` + `threshold(nN)`; `vocabulary`: the simulator's referents, one name per thing |
| `world/sw_host.py` | the host: a fired `cmd_X[…]` → the game's verb in the world's spelling (`labels`); the game's own refusal (`said(unknown)` / `said(cant)`, nothing moved); from the RESULT line, not the command: `focused(O)`, `connected(A, B)` (a move disconnects), `measured(O, nN)` (a thermometer used on O, for one beat as `said/1`; a qualified referent such as "substance in metal pot" resolved over the perception, "cup containing X" to X); score and reward never in `ports()` or the log; snapshot/restore by replay; `$METIS_SW_LOG` |
| `world/families.py` | `conductivity` (test-conductivity, …-of-unknown-substances), `melting` (measure-melting-point-known-substance, …-unknown-substance); the env's train (discovery) / dev / test (held-out) variations |
| `world/gen_instance.py` + `world/card.yaml` | a variation as a PACKAGE `domains/<task>_<n>/`: declarations + the perceived start + the task, NO rules; the card: GO, OPEN, CLOSE, TAKE, DROP, FOCUS, CONNECT(a, b), MOVE(o, c), ACTIVATE, DEACTIVATE, USE(thing, target), EXAMINE, WAIT, LOOK, UNKNOWN |
| `experiments/baseline.py` | the gold paths through the host, command by command: score 100 reproduced, the perception vector per step |
| `tests/` | the perceiver on fixed texts, the gold path winning through the host, a refusal and a restore, the package compiling |

```
METISC=../metis-lang/src/metisc ../.worlds/sw/bin/python -m pytest scienceworld/tests -q      # from the metis-worlds root
../.worlds/sw/bin/python scienceworld/experiments/baseline.py --family conductivity --n 20
../.worlds/sw/bin/python scienceworld/experiments/baseline.py --family melting --n 20
```

## What the loop must discover (step 2's hand hierarchy says it; step 3's loop finds it)

`conducts(X)` is never in the text. The circuit — battery, two wires, a bulb, X between — lit
(`state(red_light_bulb, on)` after a `wait`) says yes; dark after the wait says no. Then the
verdict: `move X to <box_if_yes|box_if_no>`.

**Melting** (step 1b): the melting point is never in the text either. Heat the substance (into a
metal pot, the pot on the stove or into the blast furnace, the device activated) or cool it (into
the freezer), and measure it with the thermometer as it goes (`use thermometer on S` →
`measured(S, nN)`). The text says when it changes state: `matter(S, solid)` becomes
`matter(S, liquid)`. The temperature then is the melting point, compared with `threshold(nN)`:
`focus on <box_if_above|box_if_below>`.

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

## Findings while building (step 1b, melting)

- **A melt renames the thing.** "solid unknown substance C" becomes "liquid unknown substance
  C", and "chocolate" becomes "liquid chocolate". The game takes only the current spelling: once
  the substance has melted, "use thermometer on solid unknown substance c" is "No known action
  matches", and the bare "unknown substance c" is never taken. The perceiver keeps ONE name, with
  the state of matter dropped (`unknown_substance_c`, `chocolate`), and puts the state in
  `matter/2`. The label follows the current spelling, so the host's command is always the one
  the game takes.
- **Water is not prefixed:** liquid water is "water", and when it freezes, "ice" takes its place
  in the cup. That is a new name, not `matter(water, solid)`: the text gives no link between the
  two, so a rule must learn that one appears where the other was. The focus, which is the
  game's, follows the object: "focus on substance in cup" answers "You focus on the water."
- **A measurement names no thing.** The result is "the thermometer measures a temperature of 35
  degrees celsius". The thing is the command's, resolved to a perceived name: the gold paths
  spell it "substance in cup", "substance in metal pot", "cup containing mercury".
- **A held thermometer has a reading** ("a thermometer, currently reading a temperature of 10
  degrees celsius" in the inventory). Step 1 read it only in the room; now `reads/2` comes from
  both.
- **One spelling per terminal:** the result line says "anode on battery is now connected to
  terminal 1 on blue wire", while a command may say "battery anode" or "cathode in red light
  bulb". The perceiver names a part owner-first (`battery_anode`, `red_light_bulb_cathode`) and
  takes the connection from the result line. The game accepts that spelling too ("connect red
  light bulb cathode to …").
- **The vocabulary shrinks:** the qualified referents ("bowl containing apple and banana…",
  "substance in cup") and a part's second spelling are dropped, so one name remains per thing:
  test-conductivity 0 goes from 495 referents to 302 names, and the melting kitchen from 141 to
  122.
- **The thermometer's range:** the `temp` type is −50…300 °C. Lead (327 °C) melts above it and
  reads n300, which is enough for every threshold the family asks (−10, 10, 50, 150, 200).

# home — the flat as a metis world (metis-worlds)

A real home under the metis agentic loop: the flat's devices through Home Assistant, the rules as
domain packages over a role vocabulary, a host that reads the home back every beat. This README is
the catalog's context: `cd home && metis-loop` (or the Claude Code metis plugin in this directory)
opens it as a workspace, and a brain reads this first.

What the home is for: the rules decide what happens to a device and say why; Home Assistant is only
the pipe to the devices; the conversation (FSTTM with Gemini, the `cloud-llm` branch) gets the home's
state as its ENVIRONMENT stream and the rules' outcomes as its REASONING stream.

## Layout

| path | what |
|---|---|
| `world/home.map.json` | the flat as data: rooms, lights, the ventilation units, the TV, the infrared devices, the sensors to come, each a role (r1, l1, u1, t1, ir1) bound to its words and its Home Assistant entity; the thresholds of the host's classes. A device with entity null is not in Home Assistant yet |
| `world/gen_map.py` | the map → `domains/shared/home_map.llp` (the role types, `light_in`, `unit_in`, `has_unit` / `no_unit`) and each package's intent handles (`--check` in CI) |
| `world/home_host.py` | the host: one World per process (Sim, or Home Assistant's REST API with `METIS_HOME_HA` and the token file `~/.config/fsttm/hass.token`), one view per package; the families kept exactly one, the timers and edges, the scene fan-out, the grace after a command |
| `domains/shared/home_world.llp` | the readings that cross packages, declarations only (presence, time of day, the units' state, the edges) |
| `domains/lights/` | lighting: on / off at a word or a scene; off in a room vacant a while; a light offered on entering a dark room at night |
| `domains/air/` | the two Prana recuperators: on / off, night / boost / normal, heater (only with the fans), winter mode; advice when it turns cold outside |
| `domains/media/` | the TV (LG webOS) on / off / louder / quieter; infrared devices by their remote's keys (the IR remote is not wired yet) |
| `domains/scenes/` | the home's mode (home, night, away): set at a word and fanned out to the other packages as one wish per device; away suggested when the home empties; the night's end suggested at dawn; arriving home ends away |
| `domains/comfort/` | advice about a room's air from the thermometers (not wired yet) and the units' state; a person's question about a room |
| `*/goldens/` | each package's scripted day and intents, and what the package says to them (`python -m metis.catalog golden <pkg>`) |
| `tests/` | the map's files current, compile and lint, the goldens byte for byte, the host's families, timers, edges, fan-out and grace, the Home Assistant mapping against a fake Home Assistant |

## Why flat packages, not a hierarchy

ALFWorld and the road are hierarchies because their activities are a sequence over one body: a
planner hands a sub-goal to a specialist and waits for its result, and a director activates who
holds the one resource (the controls). A home has no one body: the lights, the air and the TV act at
once and independently, a person speaks to any of them, and the only cross-cutting act is a scene.
So the packages are served side by side (metis-agent's orchestrator, one intent domain per package),
and a scene crosses them the way the road's commands do ('Commands as constraints'): the scenes
package decides WHAT (its own `mode`), the host fans it out as one wish per device, and each package
settles its own devices by its own rules. A director is the next step if two packages ever contend
for one device.

## The patterns the rules follow (metis-loop `skills/metis-loop/patterns`)

- **Complementary readings / Exclusive family, single reason**: every reading is a family the host
  keeps exactly one of per role (`light_lit | light_dark`, `occupied | empty | vacant | unsensed`);
  there is no negated premise. A sensor not wired is its own member (`unsensed`, `untracked`,
  `ir_absent`), so a rule needing it does not fire: the safe failure.
- **Steady reading**: thresholds with hysteresis and the vacant timer are the host's, never a
  counter in the rules; an edge (`entered`, `chilled`, `got_warm`, `left_home`, `dawn`) is asserted
  for one beat, and never from an unknown class.
- **Command → outcome**: a command token is consumed by exactly one rule per state; every outcome
  is done or refused with its `%%` sentence, and a refusal names its blocker (stopped, does not
  answer, not connected, no such device: the standing handles lx, ux, tx, irx, rx).
- **The name is the command**: the host actuates by the fired rule's name (`light_on`, `air_boost`,
  `sweep_air_night`), and gives the device GRACE beats before reading it back; a difference after
  that is the surprise the loop learns from.
- **A room is data / Bind before ground**: the rules name roles; `light_in(L, R)` and `unit_in(U, R)`
  are `bwd` facts the map generates, binding every variable at grounding.
- **Interface package**: the readings shared by packages are declared once (`shared/home_world.llp`).
- Suggestions are said, never done: away, the night's end, a light on entering, winter mode,
  ventilation for a warm or humid room. The person decides.

## semantic-world: not used (yet)

`libs/semantic-world` is for worlds whose things are uncertain and searched (a belief over places,
roles bound per goal, the RSS layer). The home's devices are fixed and read directly from Home
Assistant every beat; its rooms are data in `home.map.json`, which is all 'A room is data' needs.
Its `bayes.exists` (a log-odds per thing, raised by a sighting, decayed unseen) is the right tool for
presence once the radar is wired (several noisy zones per room, a person leaving view): revisit then.

## Not yet wired

The mmWave presence radar (`radar` in the map: a binary_sensor per room; until then every room is
`unsensed`, so `vacant_off`, `welcome_dark` and the away suggestion do not fire), the Bluetooth
thermometers (`thermometers`: temperature and humidity entities per room; until then `untracked`),
the USB infrared remote (`ir`: `ir_absent`, every IR command refused with that reason). The lights
and the TV are not in Home Assistant yet (their entities are null: refused as not answering).

## The service on the NUC (Go, on the C++ runtime)

`metis-home` (metis-agent branch `home-cgo`, `go/cmd/metis-home`) serves these packages in one native
process: the Go domain agent on libmetis_rt over cgo, the home host in Go
(`go/internal/host/home.go`, this world's `world/home_host.py` ported and held to these goldens), on a
1 s beat. Beside FSTTM's conversation it writes every outcome and conclusion to the stream door
(REASONING, 127.0.0.1:8766) and answers the tool port (127.0.0.1:8768); for Claude Code it is the runtime
`home` of the Metis surprise interface (`.metis/runtimes/home.json`; `/metis-runtime home` in a Claude
Code session with the Metis plugin here): kernel surprises written to `.metis/surprises/` then signalled,
and a package changed on disk (the user merged a rule change) reloaded, a failed load keeping the old rules.

    bash deploy/nuc/install.sh          # build natively, install the systemd user unit (starts nothing)

## Run and test

```sh
PY=../../metis-agent/py/.venv/bin/python; export METISC=../../metis-lang/src/metisc
$PY -m pytest -q tests                              # the map, the rules, the goldens, the host
$PY world/gen_map.py                                # after editing world/home.map.json
$PY -m metis.intents gen <pkg>; $PY -m metis.catalog golden <pkg>   # after editing a package
$PY -m metis.catalog.workspace context              # what a brain reads first
METIS_HOME_HA=http://127.0.0.1:8123 ...             # the host on the real home (the NUC; token file)
```

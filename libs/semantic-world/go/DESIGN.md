# semantic-world/go: the semantic world as a blackboard

The home's shared world model. Three kinds of writer fold evidence into one world:

- the sensors: Home Assistant's states, the radar, the thermometers;
- Metis: its conclusions;
- the conversation: a person's word.

Metis reads the world through its standard quantised ports. The LLM reads the same beliefs as keyed lines. The
generic core (`semworld`) knows no household. The home (`home`) is the first adapter, and road and grid adapters
can sit on the same API later.

```
 HA websocket ──Ingest──►┐                       ┌──► Board.Lines(member)  do-lines: +presence(vacant, r2) 1
 host commands ─Command─►│                       │    Board.Wake(member)   spec 15 rule 1 + rule 3
 a person ──────Report──►│  World (blackboard)   ├──► Board.Weight(port)   metis_rt_bind_weight
 Metis ─────────Conclude►│  entries → vars       │
 time ──────────Settle──►┘  belief + src + c     └──► Project(world)       env / reasoning lines (FSTTM door)
                                                      Home.State()         metis-home's HomeState families
```

## 1. The world (`semworld/world.go`)

An **entry** is a typed thing: `place | thing | agent | device | quantity | inferred`. It has a name, the place it
belongs to (`in`), attributes such as its entity ids, and **variables**. A variable is one belief, in one of four
forms:

| form | holds | written by |
|---|---|---|
| `cat` | a categorical distribution over a declared domain (`on/off`, `normal/night/boost`) | `ObserveCat` (Bayes with the sensor's reliability, after a switch transition `mix`), `SetCat`, `Report`, `Relax` (staleness) |
| `odds` | the log-odds of a binary (presence, reachability, existence), clamped ±4 as in bayes.py | `ObserveOdds` |
| `gauss` | a continuous estimate, mean ± variance (a 1-D Kalman filter with an outlier gate; the variance grows with time unheard) | `ObserveGauss`, `Gauss.Predict` |
| `fact` | a fact a Metis member asserts | `Conclude` |

Every variable carries the following fields:

- **provenance**: `src {kind: sensor|command|person|metis|prior, who, ref}`;
- `at`, the time of its last evidence;
- a change counter `c`;
- `unsure`: no evidence can reach it now, because a device is unavailable or the feed is down.

The location belief of things over places (`Doc`: `Seen`, `Missed`, `Predict`, `Walk`) is the shared bayes core.
It is held to the Python by parity (section 6) and kept for the room, grid and road adapters.

**The writers' rules:**

- **Sensors**
  - A device state is the reading folded in with reliability `R`. The prior first mixes toward the uniform with
    weight `mix`, because a light someone may switch has had time to change, so one reading is believed (94% after
    a long "off").
  - `unavailable` drives `reach` to −4 and marks the device's variables unsure. An unsure categorical forgets toward
    50/50 with a half-life (default 30 min).
- **Commands**
  - The host's own command writes its prediction at once (p 0.9, source `command`). A contrary reading inside the
    grace period (15 s) is held, not folded in.
  - After the grace a contrary or missing reading is evidence of a spec-20 *probabilistic* surprise, and the
    reading wins.
- **Persons**
  - A person's word is weak evidence (reliability 0.7, `src person`, with the utterance id as `ref`).
  - The assistant's own restatement is refused: it is not evidence.
  - A word against a sure, fresh sensor reading is not folded in. It is evidence of an *evidential* surprise.
- **Metis**
  - A Metis conclusion is kept on the member's own entry (`metis.<member>`). It is never fused into a sensed
    variable, because a conclusion drawn from the world is not new evidence about it (no double counting).
  - The LLM reads conclusions as REASONING lines. A member reads another's conclusions through a port an adapter
    offers over them; that is not built yet, see section 7.

**Surprises.** The world records evidence of surprises, never responses to them:

- a command not read back;
- a word against a sensor;
- an outlier refused.

These are spec 20's *probabilistic* and *evidential* kinds. Spec 19's statistic is a different thing: an
accumulated log Bayes factor at a choice point. It stays the runtime's job (`metis_rt_likelihood`). A single
low-probability reading is deliberately *not* called a spec-19 surprise.

## 2. The Metis face (`semworld/ports.go`)

An adapter **offers ports**: a name, its ground keys, and `P(args) → (p, known)`. A package's `domain.yaml` names
them in spec 16's own keys, so nothing new enters the manifest language:

```yaml
# domains/comfort/domain.yaml (flow lines: a composition member's reader takes no block YAML)
clock: {beats: 1, period: 60}
beliefs: {occupied: {port: present}, chill: {port: cold}}
levels: {presence: {from: {belief: present}, at: [0.3, 0.7], names: [vacant, unsure, occupied]},
         chill: {from: {belief: cold}, at: [0.5, 0.9], names: [not_cold, maybe_cold, cold]},
         outside: {from: {belief: out_cold}, at: [0.5], names: [mild_out, cold_out]}}
```

The program then reads the levels only: `$presence(vacant, R)`, `$chill(cold, R)`. The home's ports are listed
below.

| port | keys | p |
|---|---|---|
| `present(R)` | rooms with a radar | P(someone there) |
| `someone_home()` | if any radar | 1 − Π(1 − p_r) |
| `on(D)` | lights, units, TVs in HA | P(power = on) |
| `reachable(D)` | the same | P(it answers) |
| `preset(U, M)`, `one: M` | units × modes | P(mode) |
| `cold(R)`, `warm(R)` | rooms with a thermometer | P(T ≤ room_cold_c), P(T ≥ room_warm_c), from the Kalman estimate |
| `humid(R)` | the same | P(RH ≥ humid_pct) |
| `out_cold(U)` | units | P(outside ≤ outside_cold_c), only from readings taken after the unit ran `warmup` s |
| `day()` | | P(sun up) |

**The Board** serves the ports to members:

- `Join(manifest)` refuses a port the world does not offer and lists those it does.
- `Settle()` is the boundary step. It quantises every level by spec 16 §4: `names[#{t ∈ at : t ≤ p}]`, with no
  hysteresis, which belongs in the rules (spec 15 §8.5 rule 4). A port whose quantised reading changed advances
  spec 15's `c_p`, and the change is **tagged** with its source: the member for a Metis write, else `world`.
- `Wake(member, now)` is rule 1: a member beats when a port in its wake set changed since `seen_d(p)` through a
  change **not tagged with itself** (rule 3, no beat on one's own echo), or when its `clock.period` has elapsed.
- `Lines(member)` returns the do-lines that hold **exactly one level atom per known key**, retracting the previous
  atom (`-presence(occupied, r2) 1`, `+presence(vacant, r2) 1`). A key the world does not know holds no atom, so a
  rule must not read silence as a level. The lines are read once per tick: this is the one-tick instrument, with
  beliefs constant over the tick.
- `Weight(port)` is the function for `metis_rt_bind_weight`, in `rt.WeightFunc`'s shape. An unknown key prices
  1, the flat reading.
- `Check()` is spec 16 §2's sum rule (`belief-sum`) for `one:` and `lone:` ports.

**Binding on the cgo runtime.** `metis-agent/go/internal/rt` is `internal`, so this module cannot import it, and it
needs no import: the Board speaks plain Go types, and metis-agent adapts them in three lines:

```go
for _, p := range ports { prog.BindWeight(p, func(a []string, c rt.Counts) float64 { return board.Weight(p)(a, c) }) }
lines := board.Lines(pkg)          // into rt.Do(lines...) before the tick, or into the Host.Tick sync lines
if !board.Wake(pkg, now) { skip }  // when the composition runs members by rule 1
```

`semworld.Counts` has `rt.Counts`'s method set, so an `rt.Counts` passes as it is. No new exported API is needed
in metis-agent. If a public wrapper is wanted later, the set to re-export is `Load`, `Program.BindWeight`, `Do`,
`Tick`, `Host` and `Counts`.

## 3. The LLM face (`semworld/project.go`)

`Project(world, now, phrase)` is a pure function of the world. It gives one line per phrased variable, keyed by
`id.var` (the env stream replaces per key), saying:

- the value;
- a confidence word: sure ≥ 0.95, likely ≥ 0.8, probably ≥ 0.6, otherwise "unsure" with the spread
  (`unsure: on 55% / off 45%`);
- the source: sensor, commanded but not yet confirmed, said by a person, inferred by a member;
- a coarse age;
- "no fresh reading possible" when the variable is unsure.

A member's conclusions project as REASONING lines (`comfort holds advise_heater(r2) (rule cold_heater)`). A device
not in HA says so once (`living room light: not in Home Assistant yet`), and an unsensed room says nothing. This
replaces fsttm-hass's raw entity dump with the same beliefs Metis reads, so the dialog and the rules cannot
disagree about the house.

## 4. The sensor face (`home/home.go`)

| call | when |
|---|---|
| `Ingest(HAState, now)` | for every state of the initial `get_states`, then every `state_changed` `new_state` |
| `FeedDown(now)` | when the websocket drops |
| `Command(id, var, value, now)` | when the host sends a command (metis-home's `Do`, a tool call) |
| `Settle(now)` | once a beat |
| `Lines(now)`, `State()`, `B.*` | the readers |

Each `Ingest` is routed by entity id through a table built from home.map.json:

- **Fans:** a unit runs if either fan is on, and its preset comes from the supply fan.
- **Radar:** "on" is believed at once. "off" lowers presence linearly in log-odds, from sure to 0.3 over
  `vacant_after_s`, and only while the feed is up.
- **Thermometers:** each reading goes into the Kalman filter, which refuses outliers beyond 4 sd.
- **Prana outside temperature:** a reading is folded in only if it was taken after the unit had run `warmup`
  (120 s). Readings taken in the warm-up or while the unit is stopped are dropped, because they read the unit and
  not the weather. That is the 27 °C November reading.

`State()` is metis-home's `HomeState` read from the world: the likeliest values, `ok` = in HA and reachable and the
feed up, and presence `occupied | empty | ""`. The host's families, timers and edges keep working unchanged on top
of it.

## 5. Package layout and running

```
go/semworld/   bayes.go (shared core, parity) core.go (query API, Update, Relax, Gauss) world.go ports.go project.go store.go
go/home/       the home adapter + tests
go/cmd/semworld-replay/   a scripted day → env lines, members' do-lines and beats, surprises (-door: the stream door's JSON)
go/testdata/   bayes_cases.json + gen_bayes_cases.py, home.map.json (copy of metis-worlds/home), home.wired.map.json, comfort.domain.yaml, home.replay.jsonl
```

To run the tests and a replay:

```
cd libs/semantic-world/go && go test ./...
go run ./cmd/semworld-replay -member comfort=testdata/comfort.domain.yaml testdata/home.replay.jsonl
```

## 6. Parity with the Python

Parity covers what is shared: `seen`, `missed`, `predict`, `walk` (wander, biased, fractional dt), the alive decay,
and `exists`.

- `testdata/gen_bayes_cases.py` runs `semantic_world.bayes`.
- `semworld/parity_test.go` replays its cases step by step: returns, beliefs (1e-12), exists, looked, gone.
- The test bites: changing `L_HIT` or the walk's `stay` by 1e-4 fails 15 and 6 checks.
- Regenerate after any change to bayes.py with `python3 go/testdata/gen_bayes_cases.py`.

Not ported yet: `reachable`, `travel`, `interval`, `mass_within` (the road's RSS), `associate`, and the room's
`bind`. The C++ in road is only the RSS situation layer and stays the road's.

## 7. Integration steps (once the Go HA feed and metis-home's Go host land)

1. **The dependency**
   - metis-agent's `go.mod` requires `github.com/metis-lang-dev/metis-worlds/libs/semantic-world/go`. Until it is
     tagged, add a `replace` to the checkout `../../metis-worlds/libs/semantic-world/go`. The NUC has it at
     `~/metis/metis-worlds`.
2. **One world per process, in metis-home**
   - `m, _ := home.LoadMap(host.HomeMapPath(root)); world := home.New(m, home.DefaultParams)`.
3. **The HA feed becomes the sensor face**
   - The Go HA feed (the fsttm-hass port) keeps its websocket loop: `get_states`, then `subscribe_events
     state_changed`.
   - For each state, call `world.Ingest(home.HAState{EntityID, State, Attributes}, now)`. On a disconnect call
     `world.FeedDown(now)`.
   - The feed should live *inside* metis-home, or else metis-home must expose an ingest port. One process then owns
     the world. Recommended: a goroutine in metis-home.
4. **metis-home's backend**
   - Add a `HomeBackend` whose `Read()` maps `world.State()` onto `*HomeState`. The record types are field for
     field the same; copy them.
   - Its `Do(kind, role, op, value)` first calls the existing HA REST call, then
     `world.Command(role, "power"|"preset"|"heater"|"winter", value, now)`.
   - `HomeHA`'s polling of `/api/states` goes away. Keep `HomeSim` for the goldens.
5. **The beat**
   - At each beat call `world.Settle(now)` before `Readings(beat)`.
   - Then for every package, `lines := world.B.Lines(pkg)`, folded into the sync lines the host already returns
     from `Tick`.
   - Bind the weight ports once after `Load` (section 2).
6. **The manifests**
   - In metis-worlds/home, declare `beliefs:` and `levels:` in each package's `domain.yaml` (comfort's example is in
     `testdata/comfort.domain.yaml`).
   - Call `world.B.Join(semworld.ReadManifest(path, pkg))` at start. A port typo fails the start.
   - Then migrate rules from the boolean families (`cold_room(R)`) to the levels (`$chill(cold, R)`) one package at
     a time, on a branch (the user merges), with the goldens updated by the NUC Claude job.
7. **Metis writes back**
   - In metis-home's `OnEvent`, write `world.Conclude(pkg, atom, true|false, ruleName, now)` for the outcome preds
     a package marks as conclusions: the advise_* family now. Their reasoning lines go to 8766 instead of the
     hand-written `reasoning` text.
8. **The LLM projection**
   - metis-home (or the feed) sends `world.Lines(now)` to the stream door at 127.0.0.1:8766 as
     `{"stream","key","text"}`, the same format `-door` prints, only for keys whose text changed with the age
     stripped (as `semworld-replay` does).
   - Then disable fsttm-hass's raw entity dump so there is one source. FSTTM is not edited: the door protocol is
     unchanged.
9. **Persons' words** (later)
   - When the tools port gets a `home_report` intent (or Metis' intent extraction yields "I switched X on"), call
     `world.Report(person, id, var, value, 0, uttID, now)`, never with the assistant as the person.
10. **Surprises**
    - Drain `world.W.Surprises` into the workspace drop that metis-home already writes, as kind
      `probabilistic` / `evidential` with the key and the reason. Claude refines rules from them on its branch.

## 8. The world as a fold over events (`home/events.go`)

Nina's event log (nina-live) keeps the world's inputs, and the world is rebuilt by applying
them again. `Event` is the whole input alphabet:

- `ha_state`
- `feed_down`
- `command` (the host's prediction, written before the device call)
- `report`
- `conclude`
- `settle`

Each event carries its world time `At`: the world never reads a clock.

- **`Home.Apply(ev) (Out, error)`** folds one event in. Its `Out` holds the outputs, which a replay
  recomputes and never reads back:
  - the surprises it raised;
  - and, for a `settle`, every joined member's beat (`Wake`), its do-lines (`Lines`) and the
    projected lines.

  Reading the board changes it: `Lines` retracts the previous atoms, and `Wake` records what a
  member has seen. So a beat's reads belong to the settle. **A host takes its members' lines
  from `Out` and never calls `Board.Lines` or `Board.Wake` itself.**
- **`Home.Hash()`** is a checkpoint: a digest of the world, the board (`Board.State()`) and the
  adapter's own state (the pending commands, the radars, the outside readings). It is a sorted
  text walk over values, never over pointers, so NaN hashes too.
- **Determinism:**
  - The past-grace loop over pending commands now walks sorted keys. In map order, two
    commands expiring in one beat raised their surprises in a random order.
  - The remaining map loops write per key and append nothing.
- **Tests (`home/events_test.go`):**
  - `TestReplayIsDeterministic`: the test day, applied 30 times, gives the same checkpoint and
    the same outputs after every event.
  - `TestSurprisesInOrder`: four commands that expire together give the same surprises in the
    same order; it fails on the old map loop.
  - `TestHashFollowsTheWorld`.

Snapshots (a cached world at a seq) come later. Until then a start replays from genesis: a
day's events are small.

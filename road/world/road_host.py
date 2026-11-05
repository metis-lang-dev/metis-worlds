"""road_host — the road domains' host on the EXERCISER (road-world s-e812715d step 2), in mh_host's shape: each member
of road/domains (responder, planner; the director has its own) gets one, and every host of a run shares
one RoadWorld (SHARED, keyed by the run). The world's facts come from road_facts (the projection every road host makes),
the commands go through restrict (the one restrictor), so the SUMO host (step 4) speaks the same interface.

    the run: $METIS_ROAD_RUN, a JSON file {"scenario", "seed", "log"?, "world"?, ...}; without it, the cruise
                       scenario, seed 1; "world": "sumo" runs sumo_host.Loop(run) instead of the exerciser (new_world)
    reading(counts)    the world's facts (road_facts.facts), filtered to the member's world-private preds, latched at
                       the member's clock period (the planner sees the world every tenth step)
    tick(counts)       the responder's host steps the world one DT (the fast member is the world's clock); then the
                       sync: the owned preds asserted / retracted, the member's own tokens untouched
    on_event(rule)     a fired rule that is a command (restrict.command) becomes the ego's, held for the member's
                       clock period (the planner's for ten ticks, the responder's for one)
The log ($METIS_ROAD_LOG, or the run's "log"): one JSON line a world step (the ego's t, s, v, a, lane, the command,
the fold), and the run's summary at the end (summary()).

The page (the run's "page": true, road_hier.py; road-agent s-357becc7 step 1): the responder's host says the frames (road_frames.py), takes the
page's world lines (run:SCENARIO:SEED starts that run now, play, pause, speed:X, watching: a page is open, hello: it wants the road, and the Traffic dock's: traffic()) and holds each world step to its real time times the speed; one
Live beat stays one world step, as in road_tree. A new run swaps the world under the running hierarchy and gives the planner a new trip if the last one ended: the service's
new_game would re-instance the planner without its trip (so it never takes the page's button)."""
import json
import shutil
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import restrict  # noqa: E402
import road_frames  # noqa: E402
import road_wishes  # noqa: E402
import road_world  # noqa: E402
from semantic_world.ports import sync_diff  # noqa: E402

SHARED = {}                       # run key -> {"world": RoadWorld}

ROAD = os.path.dirname(HERE)      # road/


def family_home(root=None):
    """The road FAMILY's directory, the METIS_HOME every road program resolves its units through (road-family
    s-f62c0ed8; metis-catalog domains/road at road/domains/catalog.pin): $METIS_HOME if set, else the sibling
    metis-catalog checkout, else the installed catalog's package (metis.catalog.find_package). Set it in the environment
    before a REPL or metisc runs a road program; a miss names the three places."""
    env = os.environ.get("METIS_HOME")
    if env and os.path.isfile(os.path.join(env, "responder_domain.llp")):
        return env
    sib = os.path.join(os.path.dirname(os.path.dirname(ROAD)), "metis-catalog", "domains", "road")
    if os.path.isfile(os.path.join(sib, "responder_domain.llp")):
        return sib
    try:
        from metis.catalog import find_package
        p = str(find_package("road", root))
        if os.path.isfile(os.path.join(p, "responder_domain.llp")):
            return p
    except Exception:  # noqa: BLE001
        pass
    raise FileNotFoundError("the road family (responder_domain.llp) is in none of: $METIS_HOME=%r, %s, the installed catalog's "
                            "domains/road; check out metis-catalog beside (road/domains/catalog.pin)" % (env, sib))


def set_family_home():
    os.environ["METIS_HOME"] = family_home()
    return os.environ["METIS_HOME"]
DT = 0.1                          # the world's step, s
CR_LIST = 60                    # the CommonRoad picker's rows at most (the index has thousands)
WATCHED_S = 5.0                   # a page said `watching` this recently: a scene every step, else every second
UNWATCHED_EVERY = 10


def run_spec():
    p = os.environ.get("METIS_ROAD_RUN")
    if p and os.path.exists(p):
        spec = json.load(open(p))
        spec.setdefault("key", os.path.abspath(p))
        return spec
    return {"scenario": "cruise", "seed": 1, "key": "default"}


def new_world(run):
    """The run's world: the exerciser (RoadWorld), or with "world": "sumo" nina's sumo_host.Loop, which presents
    RoadWorld's face (observe, command, step, tick, t, log, arrived, summary)."""
    if run.get("world") == "sumo":
        import sumo_host
        return sumo_host.Loop(run)
    return road_world.RoadWorld(run.get("scenario", "cruise"), int(run.get("seed", 1)),
                                sensor_range=float((run.get("sensor") or {}).get("range", road_world.SENSOR_RANGE)))


def manifest(package_dir):
    p = os.path.join(package_dir, "domain.yaml")
    if not os.path.exists(p):
        return {}
    import yaml
    return yaml.safe_load(open(p)) or {}


class RoadHost:
    PAIRS = ()

    def __init__(self, package_dir, case=None):
        self.package_dir, self.case = package_dir, case
        self.spec = os.path.basename(os.path.normpath(package_dir))
        man = manifest(package_dir)
        self.observed = {p for p, d in (man.get("shared") or {}).items() if d == "world-private"}
        self.period = int(((man.get("clock") or {}).get("period")) or 1)
        self.steps = self.spec == "responder"
        run = run_spec()
        if run["key"] not in SHARED:
            SHARED[run["key"]] = {"world": new_world(run), "log": run.get("log") or os.environ.get("METIS_ROAD_LOG")}
        self.run = run
        self.shared = SHARED[run["key"]]
        self.road = self.shared["world"]           # (the world(lines) face is AgentHost's: no attribute of that name)
        self.beat, self.due, self.script, self.last = 0, (), {}, None
        self.latched, self.latched_at, self.now_due = None, None, True

    # ── the world's facts, latched at the member's clock ──
    def fresh(self):
        facts = self.road.observe()[0]
        if self.spec == "planner" and self.run.get("page"):
            w = self.shared.setdefault("wish", road_wishes.new())
            me = self.road.prev_truth.get(self.road.ego_id) if hasattr(self.road, "prev_truth") else None
            if me and hasattr(self.road, "world"):
                edge = me["lane"].rsplit("_", 1)[0]
                sides, back = self.road.world.lane_sides(edge, me["index"])
                facts = road_wishes.without_sides(facts, sides)
                side = back or self.road.world.lane_for_route()      # on a shoulder: back to a lane
                road_wishes.route_lane(w, edge, None if side in sides else side)
            road_wishes.planner_tick(w, facts)
            if me:
                road_wishes.turn_lanes(w, (me["lane"].rsplit("_", 1)[0], me["index"]))
            if hasattr(self.road, "world"):
                self.road.world.keep_going()
            self.road.pace = road_wishes.pace_limit(w)
            ego = self.road.proj.get("ego")
            facts = road_wishes.planner_facts(w, facts, ego.dyn.vmax if ego is not None else 0.0)
        if self.observed:
            return {a: n for a, n in facts.items() if a.split("(")[0] in self.observed}
        return dict(facts)

    def reading(self, counts=None):
        """The member's copy of the world: refreshed once a clock period (the planner's every tenth world step, the
        responder's every step), so a slow member's copies change, and it beats, at its own rate (the tick's rule 1);
        `now` from the refresh until the member's command (one command a period)."""
        t = self.road.tick
        if self.latched is None or self.latched_at < t - t % self.period:
            self.latched, self.latched_at, self.now_due = self.fresh(), t, True
        out = {a: n for a, n in self.latched.items() if a != "now"}
        if self.now_due:
            out["now"] = 1
        return out

    def latch(self):
        """The Live's rule 2 (the world as it stood at the boundary) is this host's own: a member reads the world at
        its clock's refresh (reading), the fast member the step it made. Nothing to snapshot here."""

    def unlatch(self):
        pass

    def observe(self, counts):
        """A world that moves by itself is no surprise. road_tree says so to its Live (watch.blind); the service has no such word, so on the page the
        watch reads what the session holds, or its first open record would leave the responder observing only."""
        return dict(counts) if self.run.get("page") else self.reading()

    def tick(self, counts):
        self.beat += 1
        if self.steps:                                 # the host that steps the world beats every tick: its count is the trace's k
            self.shared["k"] = self.beat
            if self.beat == 1:
                self.run_files()
        self.world_now()
        if self.steps and self.beat > 1 and not self.road.arrived() and not self.shared.get("paused"):
            if self.run.get("page"):
                self.pace()
            self.road.step()
            self._log(self.road.log[-1])
            self.truth_out()
            if self.run.get("page"):
                self.follow_lane()
        elif self.steps and self.run.get("page"):
            time.sleep(DT)                             # paused or there: the Live's clock has no pace of its own
        dos = self.sync(counts)
        if getattr(self, "new_trip", False):           # the last trip ended at its destination: the planner has none to drive
            self.new_trip = False
            if counts.get("trip", 0) <= 0:
                dos = list(dos or []) + ["+trip 1"]
        return dos

    def sync(self, counts):
        r = self.reading()                             # no argument: the tick's latch takes none (a copy, spec/17 amendment 4)
        return sync_diff(r, counts, self.observed or {a.split("(")[0] for a in r})

    # ── the commands ──
    def on_event(self, name, args):
        if self.spec == "task":
            self.wish(name)
            self._log({"t": round(self.road.t, 2), "member": "task", "rule": name})
            return
        cmd = restrict.command(name)
        if cmd is not None:
            self.now_due = False                       # this period's command is given
            self.road.command(cmd, life=self.period)
            self._log({"t": round(self.road.t, 2), "member": self.spec, "rule": name, "command": list(cmd)})

    def bind(self, reg):
        pass

    def world(self, lines):
        if not self.run.get("page"):
            raise ValueError("world lines: the road is the world")
        for line in lines:
            if line == "watching":
                self.shared["watched"] = time.monotonic() + WATCHED_S
            elif line == "hello":                      # a page opened: the road once, it is big
                self.shared["net_due"] = True
                self.shared["mark_due"] = True         # … and where the events stand: a reload does not start the count again
            elif line.startswith("drive:"):
                _, verb, value = (line.split(":") + [""])[:3]
                self.wish("%s[X=%s]" % (verb, value) if value else verb)
            elif line.split(":")[0] in ("traffic", "car", "lane", "lights"):
                self.traffic(line)
            elif line.startswith("mark:"):
                self.mark(line)
            elif line.startswith("crfind:"):
                self.cr_find(line[len("crfind:"):])
            elif line.startswith("run:"):
                scenario, seed = line[len("run:"):].rsplit(":", 1)        # a scenario's name may hold a colon (cr:ID, card:NAME@TOWN#SITE)
                self.start_run(dict(self.run, scenario=scenario, seed=int(seed)))
            elif line in ("play", "pause"):
                self.shared["paused"] = line == "pause"
            elif line.startswith("speed:"):
                self.shared["speed"] = max(0.1, float(line[6:]))
            else:
                raise ValueError("the road's page says run:SCENARIO:SEED, crfind:QUERY, play, pause, speed:X, mark:N:start, mark:N:stop or watching, not %r" % line)

    def cr_find(self, query):
        """The Traffic dock's CommonRoad picker (commonroad-world step 3): the checkout's index (road/maps/cr/index.json, made by
        road/setup-commonroad.sh) filtered by every word of QUERY (in the id, country, map, set, source or tags), the first CR_LIST
        rows as a world/cr_list frame, each with whether its conversion is cached (a cached one starts at once)."""
        import cr_world
        idx = cr_world.CACHE / "index.json"
        if not idx.is_file():
            self.shared["cr_list"] = {"ev": "world/cr_list", "q": query, "n": 0, "rows": [],
                                      "error": "no index of the checkout here: road/setup-commonroad.sh makes it"}
            return
        st = idx.stat().st_mtime
        if self.shared.get("cr_index_at") != st:
            self.shared.update(cr_index=json.loads(idx.read_text())["rows"], cr_index_at=st)
        words = query.lower().split()
        hits = [r for r in self.shared["cr_index"]
                if all(w in " ".join([r["id"], r.get("country", ""), r.get("map", ""), r.get("set", ""), r.get("source", ""), *r.get("tags", [])]).lower()
                       for w in words)]
        rows = [dict(r, cached=(cr_world.CACHE / r["id"] / "cr.json").is_file()) for r in hits[:CR_LIST]]
        self.shared["cr_list"] = {"ev": "world/cr_list", "q": query, "n": len(hits), "rows": rows}

    def mark(self, line):
        """A person saw a problem: mark:N:start[:TICK], then mark:N:stop[:TICK], the events numbered 1..N over the demo, to be discussed after. The line is in the journal as it came
        (dlg-world; TICK is the page's, so a saved journal says where), the row with the car's place in the run's log. The row's tick is at_tick: a `tick` makes it a tick row."""
        _, n, edge = line.split(":")[:3]
        m = self.shared.setdefault("marks", {"n": 0, "open": False})
        due = (m["n"], "stop") if m["open"] else (m["n"] + 1, "start")
        if (int(n), edge) != due:
            raise ValueError("the road's page says event %s %s, and the next is event %d %s" % (n, edge, *due))
        m.update(n=int(n), open=edge == "start")
        at = self.road.log[-1] if self.road.log else {}
        rows = [{"t": round(self.road.t, 2), "mark": int(n), "edge": edge, "at_tick": self.road.tick, "scenario": self.run.get("scenario"), "seed": self.run.get("seed"),
                 "lane": at.get("lane"), "s": at.get("s"), "v": at.get("v")}]
        self._log(rows[-1])
        self.mark_row(rows[-1])
        self.shared["mark_due"] = True
        self.shared["mark_said"] = "Event %s %s, tick %d." % (n, "started" if edge == "start" else "ended", self.road.tick)

    def wish(self, rule):
        """What the person asks, from the task's rule (the words) or the Drive dock (rule's own form): a preference for the planner, or the ego's way."""
        w = self.shared.setdefault("wish", road_wishes.new())
        name = road_wishes.take(w, rule)
        says = {"lane": "I have asked for that lane.", "pass": "I have asked to pass.", "follow": "I stay behind.", "stop": "Stopping.", "go": "Going on.", "resume": "As usual.",
                "pace": "Pace: %s." % w["pace"]}
        if name == "around":
            w["said"].append(road_wishes.around(self.road.observe()[0], self.road.observe()[1]))
        elif name == "turn":
            way = rule[rule.index("=") + 1:-1]
            done = self.road.world.turn(way) if hasattr(self.road, "world") else None
            w["turn"] = done
            w["said"].append(("Going %s at the next junction." % way if way != "straight" else "Straight on at the next junction.") if done else "There is no way %s ahead." % way)
        elif name in says:
            w["said"].append(says[name])

    def traffic(self, line):
        """The page's Traffic dock: traffic:add:KIND:N, traffic:ahead:KIND:N, traffic:clear, traffic:scale:X, car:remove:ID, car:stop:ID, car:go:ID, lane:close:ID, lane:open, lights:on, lights:off.
        A word back for each; what SUMO refuses is said too, and the run goes on."""
        w = self.road.world
        says = self.shared.setdefault("wish", road_wishes.new())["said"]
        what, _, rest = line.partition(":")
        verb, _, arg = rest.partition(":")
        try:
            if line.startswith("traffic:add") or line.startswith("traffic:ahead"):
                kind, n = arg.split(":")
                says.append("Added %d %s car%s%s." % (w.add_cars(kind, int(n), ahead=verb == "ahead"), kind, "" if n == "1" else "s", " ahead of the ego" if verb == "ahead" else ""))
            elif line == "traffic:clear":
                says.append("Removed %d cars." % w.clear_cars())
            elif verb == "scale":
                w.scale(float(arg))
                says.append("Traffic scale %s: it applies to the cars still to depart." % arg)
            elif what == "car" and arg == road_host_ego(self.road):
                says.append("The ego is the stack's: it stays.")
            elif what == "car":
                {"remove": w.remove_car, "stop": w.stop_car, "go": lambda v: w.stop_car(v, False)}[verb](arg)
                says.append("%s: %s." % (arg, {"remove": "removed", "stop": "stopped", "go": "going again"}[verb]))
            elif what == "lane" and verb == "close":
                w.close_lane(arg)
                says.append("Lane %s closed." % arg)
            elif what == "lane":
                says.append("Reopened %d lanes." % w.open_lanes())
            elif what == "lights":
                w.lights_on(verb == "on")
                says.append("Traffic lights %s." % verb)
            else:
                raise ValueError("the road's page does not say %r" % line)
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001 — TraCI's refusal, in its own words
            says.append("SUMO refused %s: %s" % (line, e))

    def follow_lane(self):
        """Every tick, an edge can be shorter than a planner's tick: the route follows the ego's lane; a turn the person asked for and the ego could not get over for is said."""
        if not hasattr(self.road, "world"):
            return
        edge = self.road.world.follow_lane()
        w = self.shared.setdefault("wish", road_wishes.new())
        if edge and w["turn"] and w["turn"][0] == edge:
            w.update(turn=None, want=None)
            w["said"].append("I could not get over in time for that turn: I go on from this lane.")

    def pace(self):
        """Hold this step until its time; a slow step is not made up after."""
        now = time.monotonic()
        due = self.shared.get("due", now)
        if due > now:
            time.sleep(due - now)
        self.shared["due"] = max(due, now) + DT / self.shared.get("speed", 1.0)

    def frames(self):
        if not (self.steps and self.run.get("page")):
            return []
        watched = self.shared.get("watched", 0) > time.monotonic()
        out = [road_frames.scene_frame(self.road)] if watched or self.beat % UNWATCHED_EVERY == 0 else []
        if self.shared.pop("net_due", False):
            out.insert(0, road_frames.net_frame(self.road))
        if self.shared.pop("mark_due", False):
            m = self.shared.get("marks", {"n": 0, "open": False})
            out.append({"ev": "world/mark", "n": m["n"], "open": m["open"], "said": self.shared.pop("mark_said", None)})
        if "cr_list" in self.shared:
            out.append(self.shared.pop("cr_list"))
        w = self.shared.get("wish")
        while w and w["said"]:
            out.append({"ev": "world/message", "text": w["said"].pop(0)})
        if self.road.arrived() and not self.shared.get("said_arrived"):
            self.shared["said_arrived"] = True
            out.append(road_frames.summary_frame(self.road))
        return out

    def start_run(self, spec):
        """The next run, now: one SUMO at a time. Every host finds the new world at its next reading (world_now). A CommonRoad
        scenario (cr:ID, commonroad-world s-9b7591fb step 3) runs on SUMO, converted into the cache first when it is not there
        (cr_world.load: the conversion venv, a few seconds); one that cannot be had is said, and the run on the page goes on."""
        said = self.shared.setdefault("wish", road_wishes.new())["said"]
        if str(spec.get("scenario", "")).startswith("cr:"):
            import cr_world
            spec = dict(spec, world="sumo")
            t0 = time.monotonic()
            try:
                cr_world.load(cr_world.scenario_id(spec["scenario"]))
            except Exception as e:                                   # noqa: BLE001 — a bad id or a failed conversion: the person is told
                said.append("I cannot run %s: %s" % (spec["scenario"], str(e)[:300]))
                return
            took = time.monotonic() - t0
        close = getattr(self.shared["world"], "close", None)
        if close:
            close()
        self.run = spec
        self.shared["world"] = new_world(spec)
        self.shared.update(paused=False, said_arrived=False, wish=road_wishes.new(), net_due=True)
        if str(spec.get("scenario", "")).startswith("cr:") and took > 1.0:
            self.shared["wish"]["said"].append("%s converted into the cache in %.0f s; it runs now." % (spec["scenario"], took))

    def world_now(self):
        """The shared world, if a new run replaced it: the copies start over. → True when it did."""
        if self.road is self.shared["world"]:
            return False
        self.road = self.shared["world"]
        self.latched, self.latched_at, self.now_due = None, None, True
        self.new_trip = self.spec == "planner"
        return True

    def pending(self):
        return False

    def trace_ref(self):
        """Where the world is at a trace's checkpoint (metis.trace): the run and its time."""
        return {"scenario": self.run.get("scenario"), "seed": self.run.get("seed"), "world": self.run.get("world", "exerciser"), "t": round(self.road.t, 2)}

    def trace_command(self, name):
        """A fired rule's command as the restrictor emits it (kind, arg), for the trace's `out`."""
        return restrict.command(name)

    def snapshot(self):
        return {"beat": self.beat}

    def restore(self, snap):
        self.beat = snap.get("beat", 0)

    def mark_row(self, row):
        """The mark beside the run's trace (loop-workspace step 5, WORKSPACE.md §6.1 item 2): the log's row with at_k, the trace's k at
        this tick (the stepping host's beat: on the road k = the log's tick + 1 within a run, and it goes on across a page's runs while the
        tick starts again), in <trace>/marks.jsonl, which the shared frontend's TRACE lists. Nothing when the run has no trace, or no tick yet."""
        d, k = self.run.get("trace"), self.shared.get("k")
        if not d or k is None:
            return
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "marks.jsonl"), "a") as f:
            f.write(json.dumps(dict(row, at_k=int(k))) + "\n")

    def truth_out(self):
        """The world's truth column beside the run's trace (spec 20 §10.2; cr-harvest s-f4e297da): TRACE/truth.jsonl, its header
        {truth: 1, cannot} first, then the world's row (truth_row: the SUMO host's) at the trace's k. Nothing without a trace, a
        k, or a world that keeps no truth (the exerciser)."""
        d, k = self.run.get("trace"), self.shared.get("k")
        row = getattr(self.road, "truth_row", None)
        if not d or k is None or row is None:
            return
        r = row()
        if r is None:
            return
        os.makedirs(d, exist_ok=True)
        f = os.path.join(d, "truth.jsonl")
        with open(f, "a") as out:
            if out.tell() == 0:
                out.write(json.dumps({"truth": 1, "cannot": list(getattr(sys.modules.get(type(self.road).__module__), "CANNOT", []))}) + "\n")
            out.write(json.dumps(dict(r, k=int(k))) + "\n")

    def run_files(self):
        """At the run's first tick (the trace's dir is made by then): the config the run is played with, copied beside its trace, so the judge
        replays this run's and a later demo's rewrite of ROOT/.run/config.yaml changes nothing (§6.1 item 3)."""
        d, c = self.run.get("trace"), self.run.get("config")
        if d and c and os.path.isfile(c) and not os.path.exists(os.path.join(d, "config.yaml")):
            os.makedirs(d, exist_ok=True)
            shutil.copyfile(c, os.path.join(d, "config.yaml"))

    def _log(self, rec):
        p = self.shared.get("log")
        if p:
            with open(p, "a") as f:
                f.write(json.dumps(rec) + "\n")


def road_host_ego(road):
    return getattr(road, "ego_id", None)


def make(case=None, package_dir=None):
    return RoadHost(package_dir or HERE, case)

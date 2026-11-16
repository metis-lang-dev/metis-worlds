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
HOST_LOADED = None                # the world model's code as this process loaded it (road_narrate.snapshot of road/world/*.py), at import
CATALOG_S = 2.0                   # the catalog watch: the domains and the family read by content every 2 s (metis-plugin step 4)


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
    if str(run.get("scenario", "")).startswith("ix:"):          # the level-k intersection (road/intersection, LEVELK.md §5)
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "intersection"))
        import intersection
        return intersection.IntersectionWorld(run["scenario"][3:], int(run.get("seed", 1)),
                                              sensor_range=float((run.get("sensor") or {}).get("range", road_world.SENSOR_RANGE)))
    return road_world.RoadWorld(run.get("scenario", "cruise"), int(run.get("seed", 1)),
                                sensor_range=float((run.get("sensor") or {}).get("range", road_world.SENSOR_RANGE)),
                                levelk=bool(run.get("levelk")))


def manifest(package_dir):
    p = os.path.join(package_dir, "domain.yaml")
    if not os.path.exists(p):
        return {}
    import yaml
    return yaml.safe_load(open(p)) or {}


def _int(v):
    return None if v in (None, "") else int(v)


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
        `now` from the refresh until the member's command (one command a period). A new run (start_run) may have swapped the world
        between this member's ticks: the reading moves to it first, never reads the closed one (the page's run picker hung the service so)."""
        self.world_now()
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
                metis_ide()                            # … and the backend looks for an attached plugin (its /ide lockfile)
                self.shared.pop("metis_up", None)      # … whose state the new page is told
                self.shared["net_due"] = True
                self.shared["mark_due"] = True         # … and where the events stand: a reload does not start the count again
                self.shared.pop("cat_said", None)      # … and a pending catalog / world-model change said again: a page that just opened
                self.shared.pop("host_said", None)     # (or reloaded) has not seen it (metis-plugin step 6)
            elif line.startswith("drive:"):
                _, verb, value = (line.split(":") + [""])[:3]
                self.wish("%s[X=%s]" % (verb, value) if value else verb)
            elif line.split(":")[0] in ("traffic", "car", "lane", "lights"):
                self.traffic(line)
            elif line.startswith("mark:"):
                self.mark(line)
            elif line.startswith("crfind:"):
                self.cr_find(line[len("crfind:"):])
            elif line == "catalog":                    # the SCENARIOS tree (loop-road-ui, the user 2026-11-07): the cards, grouped
                self.shared["catalog_out"] = {"ev": "world/catalog", "rows": self.catalog_tree(), "towns": road_frames.SCENARIO_NAMES()}
            elif line.startswith("narrate:"):          # metis-plugin step 4: the page's own narration (the pi LOOP dock is gone)
                self.narrate_line(line)
            elif line.startswith("metis:"):            # the surprise interface (metis-plugin s-df4ff191): the page asks its backend
                self.metis_line(line)
            elif line == "restart":                    # the world model (road/world/*.py) changed: the service again, on the same arguments
                self.restart_service()
            elif line == "catalog:seen":               # the page reloaded the members on the change it was shown: that state is the base
                import road_narrate as RN
                self.shared["cat_base"] = RN.snapshot(RN.catalog_files(os.environ.get("METIS_CATALOG", ""), os.environ.get("METIS_HOME")))
                self.shared.pop("cat_said", None)
            elif line.startswith("scard:"):            # one card, whole, for the WORLD CARD dock
                self.shared["catalog_out"] = self.scenario_card(line[len("scard:"):])
            elif line.startswith("run:"):
                scenario, seed = line[len("run:"):].rsplit(":", 1)        # a scenario's name may hold a colon (cr:ID, card:NAME@TOWN#SITE)
                self.start_run(dict(self.run, scenario=scenario, seed=int(seed)))
                self.shared["scenario_start"] = {"scenario": scenario, "seed": int(seed), "at": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())}
            elif line in ("play", "pause"):
                self.shared["paused"] = line == "pause"
            elif line.startswith("speed:"):
                self.shared["speed"] = max(0.1, float(line[6:]))
            else:
                raise ValueError("the road's page says run:SCENARIO:SEED, crfind:QUERY, play, pause, speed:X, mark:N:start, mark:N:stop, mark:N:once:KIND, "
                                 "mark:N:move:K0:K1, narrate:N:RUN:K0:K1, catalog:seen or watching, not %r" % line)

    def narrate_line(self, line):
        """narrate:N:RUN:K0:K1 → world/narration {n, run, k0, k1, members, text}: the window of the page's own trace told in the rules'
        own words (road_narrate.narrate), or its error; the run's name may hold no colon (road_hier's names: SCENARIO-SEED-TIME)."""
        import road_narrate as RN
        try:
            _, n, run, k0, k1 = line.split(":")
            out = RN.narrate(os.environ.get("METIS_CATALOG", ""), run, int(k0), int(k1))
            self.shared["narr_out"] = {"ev": "world/narration", "n": int(n), "run": run, "k0": int(k0), "k1": int(k1), **out}
        except (ValueError, OSError) as e:
            self.shared["narr_out"] = {"ev": "world/narration", "n": line.split(":")[1] if line.count(":") >= 1 else None, "error": str(e)}

    def metis_line(self, line):
        """metis:send:<json> (a person's event: written into the workspace, then signalled to the attached plugin) or
        metis:explain:<json> (a question for it). Off the tick: a kept window copies files. The answer is a world/metis_ack frame."""
        _, op, body = line.split(":", 2)
        try:
            b = json.loads(body)
        except ValueError:
            self.metis_ack({"op": op, "ok": False, "error": "not a JSON body"})
            return
        metis_ide()

        def work():
            try:
                if op == "send":
                    self.metis_ack({"op": op, "n": b.get("n"), "ok": True, **page_mark(b)})
                elif op == "explain":
                    about = {"run": b.get("run"), "k0": (b.get("window") or [None])[0], "k1": (b.get("window") or [None, None])[1],
                             "surprise": b.get("sid")}
                    self.metis_ack({"op": op, "n": b.get("n"), "ok": True, **page_request(about, b.get("words"), b.get("mode") or "explain")})
                else:
                    raise ValueError("metis:send or metis:explain, not metis:%s" % op)
            except (ValueError, KeyError, OSError) as e:
                self.metis_ack({"op": op, "n": b.get("n"), "ok": False, "error": str(e)})
        import threading
        threading.Thread(target=work, daemon=True, name="metis-%s" % op).start()

    def metis_ack(self, ack):
        self.shared.setdefault("metis_out", []).append({"ev": "world/metis_ack", **ack})

    def metis_frames(self):
        """The page's view of the surprise interface (RUNTIME-INTERFACE v1.5: the road UI's service embeds the runtime 'road-ui'
        and, under /ide, is an ide client): the run edges and ticks to its own feed, the feedback of EITHER path relayed once (the
        fan-out is the backend's; the page never sees a token), the acks of the page's requests, the attachment's state."""
        out = list(self.shared.pop("metis_out", []) or [])
        feed = runtime_feed()
        if feed is not None and self.run.get("trace"):
            trace = os.path.basename(self.run["trace"])
            st = self.shared.get("scenario_start") or {"scenario": self.run.get("scenario"), "seed": self.run.get("seed"), "at": trace}
            run = "%s-%s-%s" % (st.get("scenario"), st.get("seed"), st.get("at"))   # a run per scenario start (RUNTIME v1.5: an embedding)
            if FEED.get("run") != run:                     # its trace stays the service's (one Live: the page's runs go on in it)
                if FEED.get("run"):
                    feed.run_ended(FEED["run"], "done")
                FEED["run"] = run
                feed.run_started(run, "traces/" + trace, {k: st.get(k) for k in ("scenario", "seed") if st.get(k) is not None})
            FEED["trace"] = trace
            watch_hook(feed)
            if self.shared.get("k") is not None:
                k = int(self.shared["k"])
                feed.tick(k)
                feed.segment_closed(k - 1)                  # a queued finding (the kernel watch's) once its window is on disk
        for m in feedback():
            out.append({"ev": "world/metis", "msg": m})
        up = attached()
        if self.shared.get("metis_up") != up:
            self.shared["metis_up"] = up
            out.append({"ev": "world/metis_state", "connected": up})
        return out

    def restart_service(self):
        """The world model's code changed (a host fix, metis-plugin step 6): a reload cannot take Python already loaded, so the service
        runs again in this process, on its own arguments and environment (os.execv of sys.orig_argv); its SUMO goes with it, the page
        reloads when the service answers again (world.js onReopen)."""
        try:
            self.road.close()
        except Exception:                                  # noqa: BLE001 — a world already gone: the exec ends it anyway
            pass
        stop_runtime("restart")                          # the runtime's run ends with this process: its clients re-attach to the next
        try:
            fresh_trace(sys.orig_argv, os.environ.get("METIS_ROAD_RUN"))
        except Exception as e:                             # noqa: BLE001 — the restart goes on; the trace dir is said
            print("[road] restart: the trace dir stays (%s)" % e, flush=True)
        sys.stdout.flush(); sys.stderr.flush()
        os.execv(sys.executable, list(sys.orig_argv))

    def host_watch(self):
        """road/world/*.py by content (the world model's code), every CATALOG_S: world/host_changed, once per new state. Its base is the
        code this process loaded (HOST_LOADED, at import), so only a restart clears it."""
        import road_narrate as RN
        now = time.monotonic()
        if now - self.shared.get("host_at", 0) < CATALOG_S:
            return None
        self.shared["host_at"] = now
        snap = RN.snapshot(RN.host_files(HERE))
        base = HOST_LOADED if HOST_LOADED is not None else snap
        moved = RN.changed(base, snap)
        key = ",".join("%s=%s" % (k, snap.get(k)) for k in moved)
        if not moved or self.shared.get("host_said") == key:
            return None
        self.shared["host_said"] = key
        return {"ev": "world/host_changed", "changed": [os.path.relpath(p, ROAD) for p in moved][:40], "count": len(moved)}

    def catalog_watch(self):
        """The catalog changed on disk (Claude Code edits, builds and commits it; the page offers the reload): the road's domains and the
        family (METIS_HOME) by content, every CATALOG_S; one world/catalog_changed per new state, with the files."""
        import road_narrate as RN
        now = time.monotonic()
        if now - self.shared.get("cat_at", 0) < CATALOG_S:
            return None
        self.shared["cat_at"] = now
        root, fam = os.environ.get("METIS_CATALOG", ""), os.environ.get("METIS_HOME")
        snap = RN.snapshot(RN.catalog_files(root, fam))
        base = self.shared.setdefault("cat_base", snap)
        moved = RN.changed(base, snap)
        key = ",".join("%s=%s" % (k, snap.get(k)) for k in moved)
        if not moved or self.shared.get("cat_said") == key:
            return None
        self.shared["cat_said"] = key
        return {"ev": "world/catalog_changed", "changed": RN.rel(moved, root, fam)[:40], "count": len(moved)}

    def catalog_rows(self):
        def one_word(v):                                            # §6b: a card's one-word standing is SUMO's when present, else the exerciser's
            v = v or {}
            if "status" in v:
                return v["status"]
            for host in ("sumo", "exerciser"):
                if (v.get(host) or {}).get("status") not in (None, "skip"):
                    return v[host]["status"]
            return None
        """The scenario catalog's rows (road/docs/SCENARIO-CARD.md §7): road/catalog/index.json when the runner wrote it, else built
        from the cards (road/catalog/<source>/*.yaml) as they are. Each row: id, source, set "catalog", tags, verdict, map, and `run`,
        the scenario the page starts: a CARLA card at its first site on its town, a CommonRoad one as cr:ID."""
        import scenario_cards as C
        import yaml
        idx = C.ROAD / "catalog" / "index.json"
        if idx.is_file():
            return json.loads(idx.read_text()).get("rows") or []
        rows = []
        for f in sorted((C.ROAD / "catalog").glob("*/*.yaml")):
            try:
                c = yaml.safe_load(f.read_text())
            except Exception:                                      # noqa: BLE001 — an unreadable card is left out of the picker, not the page
                continue
            src, town = c.get("source") or {}, (c.get("map") or {}).get("town")
            if src.get("suite") == "commonroad":
                run = "cr:%s" % c["scenario"]
            elif town:
                want = ((c.get("sites") or {}).get("towns") or {}).get(town)
                first = 0 if want == "all" or not want else want[0]
                run = "card:%s@%s#%s" % (c["scenario"], town, first)
            else:
                continue
            rows.append({"id": c["scenario"], "set": "catalog", "source": f.parent.name, "tags": c.get("tags") or [],
                         "verdict": one_word(c.get("verdict")), "map": town or (c.get("map") or {}).get("net"), "run": run,
                         "country": "", "cached": True})
        return rows

    # the situation a card is filed under in the page's tree: its most specific tag (road/docs/SCENARIO-CARD.md's tags)
    SITUATIONS = ["pedestrian-crossing", "cyclist", "emergency-vehicle", "cut-in", "oncoming-pass", "turning-left", "right-before-left",
                  "merge-zipper", "highway-ramp", "obstacle-static", "lane-change", "junction-priority", "following", "lane-keeping",
                  "route-following", "speed-limit"]

    def catalog_tree(self):
        """The scenario catalog for the page's SCENARIOS tree: a row per card (road/catalog/<source>/*.yaml) with its title, suite, the
        situation it is filed under, its standing (verdict, set) and the runs it can start here: a CARLA card at each of its town sites
        (card:NAME@TOWN#SITE), a CommonRoad card as cr:ID; a card for another world (ours: the intersection) runs nowhere on this page."""
        import scenario_cards as C
        import yaml
        rows = []
        for f in sorted((C.ROAD / "catalog").glob("*/*.yaml")):
            try:
                c = yaml.safe_load(f.read_text())
            except Exception:                                      # noqa: BLE001 — an unreadable card is left out of the tree
                continue
            src, mp = c.get("source") or {}, c.get("map") or {}
            tags = c.get("tags") or []
            runs = []
            if src.get("suite") == "commonroad":
                runs = [{"label": "CommonRoad", "run": "cr:%s" % c["scenario"]}]
            elif mp.get("town"):
                towns = (c.get("sites") or {}).get("towns") or {mp["town"]: "all"}
                for town, sites in towns.items():
                    for i in ([0] if sites == "all" or not sites else sites):
                        runs.append({"label": "%s site %s" % (town, i), "run": "card:%s@%s#%s" % (c["scenario"], town, i)})
            v = c.get("verdict") or {}
            word = next((v[h]["status"] for h in ("sumo", "exerciser") if (v.get(h) or {}).get("status") not in (None, "skip")), v.get("status"))
            kind, prov = self.cr_provenance(src) if src.get("suite") == "commonroad" else (None, None)
            rows.append({"id": c["scenario"], "source": f.parent.name, "suite": src.get("suite"), "title": c.get("title") or c["scenario"],
                         "kind": kind, "provenance": prov,
                         "situation": next((t for t in self.SITUATIONS if t in tags), tags[0] if tags else "other"), "tags": tags,
                         "verdict": word, "set": c.get("set"), "runs": runs, "world": mp.get("world")})
        return rows

    @staticmethod
    def cr_provenance(src):
        """A CommonRoad card's kind and provenance (CommonRoad's own tree: scenarios/<recorded|interactive>/<scenario-factory|hand-crafted|
        SUMO|NGSIM|...>/): from the source's code path, else its type (kind/provenance); unknown, (other, other)."""
        import re
        m = re.search(r"/(recorded|interactive)/([^/]+)/", "/" + str(src.get("code") or ""))
        if m:
            return m.group(1), m.group(2)
        t = str(src.get("type") or "")
        return tuple(t.split("/", 1)) if "/" in t else ("other", "other")

    def scenario_card(self, name):
        """world/scard: the card NAME as it is on disk (its yaml), with its runs, for the page's WORLD CARD."""
        import scenario_cards as C
        import yaml
        hits = [f for f in (C.ROAD / "catalog").glob("*/%s.yaml" % name) if "/" not in name and ".." not in name]
        if not hits:
            return {"ev": "world/scard", "id": name, "error": "no card %s in road/catalog" % name}
        card = yaml.safe_load(hits[0].read_text())
        row = next((r for r in self.catalog_tree() if r["id"] == name), {})
        return {"ev": "world/scard", "id": name, "source": hits[0].parent.name, "card": card, "runs": row.get("runs", [])}

    def cr_find(self, query):
        """The Traffic dock's CommonRoad picker (commonroad-world step 3): the checkout's index (../.worlds/cr-cache/index.json, made by
        road/setup-commonroad.sh) filtered by every word of QUERY (in the id, country, map, set, source or tags), the first CR_LIST
        rows as a world/cr_list frame, each with whether its conversion is cached (a cached one starts at once)."""
        import cr_world
        idx = cr_world.CACHE / "index.json"
        catalog = self.catalog_rows()                              # the catalog's cards first, the raw checkout second (§7)
        if not idx.is_file() and not catalog:
            self.shared["cr_list"] = {"ev": "world/cr_list", "q": query, "n": 0, "rows": [],
                                      "error": "no index of the checkout here: road/setup-commonroad.sh makes it"}
            return
        st = idx.stat().st_mtime if idx.is_file() else None
        if st is not None and self.shared.get("cr_index_at") != st:
            self.shared.update(cr_index=json.loads(idx.read_text())["rows"], cr_index_at=st)
        words = query.lower().split()
        hits = [r for r in catalog + (self.shared.get("cr_index") or [])
                if all(w in " ".join(str(x or "") for x in [r["id"], r.get("country"), r.get("map"), r.get("set"), r.get("source"), r.get("verdict"), *(r.get("tags") or [])]).lower()
                       for w in words)]
        rows = [r if r.get("set") == "catalog" else dict(r, cached=(cr_world.CACHE / r["id"] / "cr.json").is_file()) for r in hits[:CR_LIST]]
        self.shared["cr_list"] = {"ev": "world/cr_list", "q": query, "n": len(hits), "rows": rows}

    def mark(self, line):
        """A person saw a problem: mark:N:start[:TICK], then mark:N:stop[:TICK], the events numbered 1..N over the demo, to be discussed after. The line is in the journal as it came
        (dlg-world; TICK is the page's, so a saved journal says where), the row with the car's place in the run's log. The row's tick is at_tick: a `tick` makes it a tick row.
        loop-road-ui (the user, 2026-11-07): mark:N:once:KIND — a one-off event (the page's surprise: a violation, a collision), its start and
        stop at this tick, numbered as the next event, never while one is open (the page ends it first); mark:N:move:K0:K1 — event N, ended,
        moved on the dashboard to the trace's k K0..K1: a start and a stop row again in marks.jsonl (the last pair is the window), moved: true."""
        parts = line.split(":")
        _, n, edge = parts[:3]
        m = self.shared.setdefault("marks", {"n": 0, "open": False})
        if edge == "move":
            return self.mark_move(m, int(n), *parts[3:7])
        if edge == "once":
            if m["open"]:
                raise ValueError("the road's page says event %s once, and event %d is open: end it first" % (n, m["n"]))
            if int(n) != m["n"] + 1:
                raise ValueError("the road's page says event %s once, and the next is event %d" % (n, m["n"] + 1))
            kind = parts[3] if len(parts) > 3 and parts[3] else "surprise"
            m.update(n=int(n), open=False)
            at = self.road.log[-1] if self.road.log else {}
            base = {"t": round(self.road.t, 2), "mark": int(n), "at_tick": self.road.tick, "scenario": self.run.get("scenario"), "seed": self.run.get("seed"),
                    "lane": at.get("lane"), "s": at.get("s"), "v": at.get("v"), "kind": kind}
            for e in ("start", "stop"):
                self._log(dict(base, edge=e))
                self.mark_row(dict(base, edge=e))
            self.shared["mark_due"] = True
            self.shared["mark_said"] = "Event %s: a %s at tick %d. The run is paused." % (n, kind, self.road.tick)
            return
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

    def mark_move(self, m, n, k0, k1, tick0=None, tick1=None):
        """Event N moved to the trace's k K0..K1 (the dashboard's drag): a start and a stop row at those k in marks.jsonl, the log the same
        rows. Their at_tick is the page's (mark:N:move:K0:K1:TICK0:TICK1: the run's tick at those k; the k goes on while the run is paused,
        the tick does not, so the host does not derive it); without them, none. Only an event there was, and ended."""
        (k0, tick0), (k1, tick1) = sorted([(int(k0), _int(tick0)), (int(k1), _int(tick1))])
        if not 1 <= n <= m["n"] or (m["open"] and n == m["n"]):
            raise ValueError("the road's page moves event %d, and there are events 1..%d%s" % (n, m["n"], ", the last open" if m["open"] else ""))
        for e, k, tick in (("start", k0, tick0), ("stop", k1, tick1)):
            row = {"t": None if tick is None else round(tick * DT, 2), "mark": n, "edge": e, "at_tick": tick, "scenario": self.run.get("scenario"),
                   "seed": self.run.get("seed"), "moved": True}
            self._log(row)
            d = self.run.get("trace")
            if d and self.shared.get("k") is not None:
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, "marks.jsonl"), "a") as f:
                    f.write(json.dumps(dict(row, at_k=k)) + "\n")
        self.shared["mark_due"] = True
        self.shared["mark_said"] = ("Event %d moved to %.1f–%.1f s." % (n, tick0 * DT, tick1 * DT)) if tick0 is not None and tick1 is not None \
            else "Event %d moved to k %d–%d." % (n, k0, k1)

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

    def holds_beat(self):
        """The page's pause holds the beat (metis-agent Live.beat_held; the user, 2026-11-07: "we simulate in lock step, not realtime"):
        no member ticks, the trace's k stays, so a paused page keeps its events in the trace's ring."""
        return bool(self.run.get("page") and self.shared.get("paused"))

    def frames(self):
        if not (self.steps and self.run.get("page")):
            return []
        watched = self.shared.get("watched", 0) > time.monotonic()
        out = [self.scene()] if watched or self.beat % UNWATCHED_EVERY == 0 else []
        if self.shared.pop("net_due", False):
            out.insert(0, road_frames.net_frame(self.road))
        if self.shared.pop("mark_due", False):
            m = self.shared.get("marks", {"n": 0, "open": False})
            out.append({"ev": "world/mark", "n": m["n"], "open": m["open"], "said": self.shared.pop("mark_said", None)})
        if "cr_list" in self.shared:
            out.append(self.shared.pop("cr_list"))
        if "catalog_out" in self.shared:
            out.append(self.shared.pop("catalog_out"))
        if "narr_out" in self.shared:
            out.append(self.shared.pop("narr_out"))
        for fr in (self.catalog_watch(), self.host_watch()):     # the catalog (a reload) and the world model's code (a restart)
            if fr:
                out.append(fr)
        out += self.metis_frames()
        if "run_out" in self.shared:
            out.append(self.shared.pop("run_out"))
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
        if str(spec.get("scenario", "")).startswith("cr:"):
            import cr_world
            spec = dict(spec, world="sumo")
            t0 = time.monotonic()
            try:
                cr_world.load(cr_world.scenario_id(spec["scenario"]))
            except Exception as e:                                   # noqa: BLE001 — a bad id or a failed conversion: the person is told
                self.run_failed(spec, str(e))
                return
            took = time.monotonic() - t0
        was, old = self.run, self.shared["world"]
        close = getattr(old, "close", None)
        if close:
            close()
        try:
            world = new_world(spec)
        except Exception as e:                                       # noqa: BLE001 — SUMO that would not start (TraCI's retries): the page is told,
            self.run_failed(spec, str(e))                            # and the run before it starts again, never a closed world left under the hosts
            try:
                self.shared["world"] = new_world(was)
                self.shared.update(net_due=True)
            except Exception as e2:                                  # noqa: BLE001
                self.run_failed(was, "the run before it did not start again either: %s" % e2)
            return
        self.run = spec
        self.shared["world"] = world
        self.shared.update(paused=False, said_arrived=False, wish=road_wishes.new(), net_due=True)
        if str(spec.get("scenario", "")).startswith("cr:") and took > 1.0:
            self.shared["wish"]["said"].append("%s converted into the cache in %.0f s; it runs now." % (spec["scenario"], took))

    def run_failed(self, spec, why):
        """A run that could not start: said in TALK and in the SCENARIOS card (world/runfail), the page never left waiting in silence."""
        why = " ".join(str(why).split())[:400] or "no reason given"
        self.shared.setdefault("wish", road_wishes.new())["said"].append("I cannot run %s: %s" % (spec.get("scenario"), why))
        self.shared["run_out"] = {"ev": "world/runfail", "scenario": spec.get("scenario"), "seed": spec.get("seed"), "why": why}

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

    def scene(self):
        """The scene frame, with the trace's k and the run's trace name (loop-road-ui: the page's events name their window in the trace)."""
        f = road_frames.scene_frame(self.road)
        if self.shared.get("k") is not None:
            f["k"] = int(self.shared["k"])
        if self.run.get("trace"):
            f["trace"] = os.path.basename(self.run["trace"])
        return f

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


def fresh_trace(argv, run_json=None):
    """A restart's trace is a NEW dir (step 6: the restart re-read the same config, rewrote the dir from seg-0 and left the last start's
    later segments beside it, a trace no replay can read): the config's trace.dir and run.json's trace get this moment's stamp."""
    import re
    import yaml
    argv = list(argv)
    if "--config" not in argv:
        return None
    cfg = argv[argv.index("--config") + 1]
    c = yaml.safe_load(open(cfg))
    old = (c.get("trace") or {}).get("dir")
    if not old:
        return None
    now = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())      # run names <stem>-<UTC stamp>, as the generic runtime's (RUNTIME-INTERFACE)
    new = re.sub(r"\d{8}T\d{6}Z?$", now, old) if re.search(r"\d{8}T\d{6}Z?$", old) else "%s-%s" % (old, now)
    c["trace"]["dir"] = new
    yaml.safe_dump(c, open(cfg, "w"), sort_keys=False)
    if run_json and os.path.isfile(run_json):
        r = json.load(open(run_json))
        r["trace"] = new
        json.dump(r, open(run_json, "w"), indent=1)
    return new


IDE = {}
FEED = {}
RUNTIME_NAME = os.environ.get("METIS_RUNTIME_NAME", "road-ui")   # the page's runtime; the headless road runner's is 'road'
FEEDBACK = ("surprise.taken", "surprise.tried", "surprise.ruled", "surprise.applied", "explain.answer", "catalog.changed", "world.changed")


def runtime_feed():
    """The road UI's service EMBEDS the generic runtime (metis-agent metis_agent/runtime/feed.py; RUNTIME-INTERFACE v1.5): its feed
    named RUNTIME_NAME, its discovery file in this workspace, so a plugin's /connect-runtime road-ui attaches to the page's runs. None
    when the runtime package is not there (an older metis-agent): the page then has only the /ide path."""
    if "feed" not in FEED:
        try:
            from metis_agent.runtime.feed import RuntimeFeed
        except ImportError:
            FEED["feed"] = None
            return None
        import atexit
        f = RuntimeFeed(os.environ.get("METIS_CATALOG", ""), RUNTIME_NAME, domain="road")
        f.start()
        FEED.update(feed=f, since=0, seen=set())
        atexit.register(stop_runtime, "stopped")
    return FEED["feed"]


def watch_hook(feed):
    """The kernel watch's surprises as findings (RUNTIME v1.5; bond004's service.Live hook): the process's Live
    (service.Live.current) calls on_finding({kind: watch, k, member, words, record, difference}); the embedding queues it on its
    feed under the service's trace (its window is in that trace's ticks). Set once; nothing when the agent has no such hook."""
    if FEED.get("hooked"):
        return
    try:
        from metis_agent.service import Live
    except ImportError:
        return
    live = getattr(Live, "current", None)
    if live is None or not hasattr(live, "on_finding"):
        return

    def on_finding(f):
        feed.finding(dict(f, run=FEED.get("trace") or f.get("run")))
    live.on_finding = on_finding
    FEED["hooked"] = True


def stop_runtime(reason="stopped"):
    f = FEED.get("feed")
    if f is None or FEED.get("stopped"):
        return
    FEED["stopped"] = True
    try:
        if FEED.get("run"):
            f.run_ended(FEED["run"], reason)
        f.stop()
    except Exception:                                      # noqa: BLE001 — the process is going anyway
        pass


def attached():
    """Some agent hears the page: an ide pairing, or a client on the page's runtime feed."""
    ide, f = IDE.get("client"), FEED.get("feed")
    return bool((ide is not None and ide.status()["connected"]) or (f is not None and f.clients))


def feedback():
    """The feedback of both paths (the /ide client's and the runtime feed's clients'), each signal ONCE (by type and id)."""
    msgs = []
    ide = IDE.get("client")
    if ide is not None:
        msgs += ide.take()
    f = FEED.get("feed")
    if f is not None:
        got = f.after(FEED.get("since", 0))
        if got:
            FEED["since"] = max(g["seq"] for g in got)
        msgs += [g for g in got if g.get("type") in FEEDBACK and g.get("from") != f.me]
    out, seen = [], FEED.setdefault("seen", set())
    for m in msgs:
        k = (m.get("type"), m.get("id"), m.get("text") if m.get("type") == "explain.answer" else None, tuple(m.get("paths") or ()))
        if m.get("type") in FEEDBACK and k in seen:
            continue
        if m.get("type") in FEEDBACK:
            seen.add(k)
        out.append(m)
    return out


def page_mark(b):
    """A person's mark from the page, WRITTEN at once (RUNTIME-INTERFACE §4: finding(f, now=True)) through the embedded runtime: the
    SDK's drop_window under the page mark's key; surprise.new on the runtime's feed; and to an /ide-paired plugin too (one key, one
    record: spec §5). Without the runtime package: the ide client writes it (its own drop_window path)."""
    k0, k1, n = int(b["window"][0]), int(b["window"][1]), b.get("n")
    key = "%s:mark:%s:%d-%d" % (b["run"], n if n is not None else "-", k0, k1)
    page = {x: b.get(x) for x in ("n", "scenario", "seed", "t0", "t1") if b.get(x) not in (None, "")}
    ide, f = metis_ide(), runtime_feed()
    if f is None:
        return ide.surprise(b["run"], k0, k1, b.get("words"), key, member=b.get("member"), kind=b.get("kind") or "mark", extra={"page": page})
    seq0 = next(iter(f.after(0)[-1:]), {}).get("seq", 0)
    sid = f.finding({"kind": b.get("kind") or "mark", "run": b["run"], "k": k1, "k0": k0, "k1": k1, "key": key,
                     "words": b.get("words"), "member": b.get("member"), "page": page}, now=True)
    if not sid:
        why = next((s.get("error") for s in f.after(seq0) if s.get("type") == "finding.refused" and s.get("key") == key), None)
        raise ValueError(why or "the workspace refused the mark")
    rec = f.ws.surprise(sid)
    signalled = bool(f.clients)
    if ide.status()["connected"]:
        try:
            ide.signal({"type": "surprise.new", "id": sid, "ref": ".metis/surprises/%s.json" % sid, "key": key,
                        "kind": b.get("kind") or "mark", "member": rec.get("member")})
            signalled = True
        except ValueError:
            pass
    return {"id": sid, "ref": ".metis/surprises/%s.json" % sid, "key": key, "member": rec.get("member"), "trace": rec.get("trace"),
            "signalled": signalled}


def page_request(about, words, mode="explain"):
    """The page's explain / narrate request, by the route rule (RUNTIME-INTERFACE §5): the /ide pairing when connected, else the
    runtime feed's clients, else refused in words (never silence)."""
    import secrets
    ide, f = metis_ide(), runtime_feed()
    if ide.status()["connected"]:
        return ide.explain(about, words, mode=mode)
    if f is not None and f.clients:
        rid = "x%s-%s" % (time.strftime("%Y%m%dT%H%M%S"), secrets.token_hex(2))
        r = f.request("explain.request", {"id": rid, "mode": mode, "about": about, "words": " ".join(str(words or "").split())})
        if r.get("delivered"):
            return {"id": rid, "via": "runtime"}
    raise ValueError("no Claude Code is attached: /ide in a Claude Code session in this workspace, or /connect-runtime %s" % RUNTIME_NAME)


def metis_ide():
    """The backend's ONE /ide client (spec v1.1 §1: a UI backend pairs with one plugin), started at its first use and looking for
    the plugin's lockfile in this workspace from then on."""
    if "client" not in IDE:
        from metis_agent.runtime.ide_client import IdeClient   # the generic client (metis-agent; RUNTIME-INTERFACE v1.2): road keeps the glue
        import road_narrate as RN
        IDE["client"] = IdeClient(os.environ.get("METIS_CATALOG", ""), name="road-ui", domain="road", member_of=RN.member_of).start()
    return IDE["client"]


def _host_loaded():
    global HOST_LOADED
    try:
        import road_narrate as RN
        HOST_LOADED = RN.snapshot(RN.host_files(HERE))
    except Exception:                                      # noqa: BLE001 — no watch then, never a broken host
        HOST_LOADED = None


_host_loaded()

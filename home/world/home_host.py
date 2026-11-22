"""The home's host: one world (the flat, simulated or through Home Assistant) and one view of it per
package (lights, air, media, scenes, comfort). Home Assistant is a pipe: no rule lives there.

Every package's manifest names a factory here (`host: ../../world/home_host.py:lights`). The views
share one World per process, so a scene set in the scenes package reaches the lights, air and media
packages as wishes (sweep_*), each settled by its own rules ('Commands as constraints').

A view, one beat (`tick`):
  1. the outcome tokens of the last beat retracted (the host 'narrates' them: the agent reads them first);
  2. the package's readings brought to what the world says: each family with exactly one member per
     role ('Complementary readings', 'Exclusive family, single reason'). A device the program just
     switched is not read back for GRACE beats: it is given time to obey; after that a difference is
     corrected, and it is the surprise the loop learns from (it did not obey, or it was switched by hand);
  3. the package's events for one beat (an edge: entered(r), left_home, chilled(u), got_warm(r), dawn)
     and its scene wishes.
A fired rule (`on_event`) is the command: its name says what to do ('The name is the command').

The levels (metis-lang spec/16 §4): a package whose domain.yaml declares beliefs:/levels: reads, beside
the families, one level atom per key the semantic world knows (presence(maybe_someone, r3),
power(unconfirmed, u1), chill(maybe_cold, r1), outside(cold_out, u2)), none for a key it does not know.
metis-home serves them from the semantic world (metis-worlds libs/semantic-world/go); this host gives
the same atoms from its simulated state (LEVELS, the world's numbers in small): presence decaying while
the radar says nobody, a unit's power unconfirmed for the grace after a command, a thermometer's spread
growing while it is unheard (+stale(r1, 3000)), the outside air read only after the unit's warm-up.

An edge is from a known class to another: the first reading after unknown (a sensor's start) is
no edge, so a start never sounds an alarm.

Classes with a threshold have hysteresis in the host, never a counter in the rules ('Steady
reading'): the outside cold, a room cold / warm / humid, vacant after a time empty.

Backends: Sim (a table in memory: the tests, the goldens, a run without Home Assistant) and HA
(Home Assistant's REST API: METIS_HOME_HA=http://127.0.0.1:8123 and the token file
~/.config/fsttm/hass.token, never in the repo). Hardware not yet wired: the presence radar
(unsensed), the Bluetooth thermometers (untracked), the USB IR remote (ir_absent): each map entry
null, each read as its 'not wired' member, so a rule that needs it does not fire."""
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAP_PATH = Path(os.environ.get("METIS_HOME_MAP") or HERE / "home.map.json")
GRACE = 3                          # beats a switched device is given before it is read back
BEAT_S = 1.0                       # the manifests' clock period, for the host's timers
STANDING = {"lx", "ux", "tx", "irx", "rx"} | {    # + the unnamed handles (la, ua): a device named without its room
    u["handle"] for k, u in json.loads(MAP_PATH.read_text()).get("unnamed", {}).items() if not k.startswith("_")}

OUTCOMES = {                        # per package: the tokens a beat leaves, retracted at the next
    "lights": ("done", "refused", "switched", "kept", "missed", "auto_off", "suggest_light"),
    "air": ("done", "refused", "switched", "kept", "missed", "advise_winter", "noted"),
    "media": ("done", "refused", "switched", "kept", "missed", "sent"),
    "scenes": ("done", "refused", "began", "suggest", "welcomed"),
    "comfort": ("advise_air", "advise_heater", "advise_open", "noted", "said", "refused"),
}
EVENTS = {                          # per package: the one-beat events it reads
    "lights": ("entered",), "air": ("chilled",), "media": (),
    "scenes": ("left_home", "came_home", "dawn"), "comfort": ("got_cold", "got_warm", "got_humid"),
}
SWEEPS = {                          # a scene -> per package, the wish pred and which roles get it
    "night": {"lights": ("sweep_off", "lights"), "air": ("sweep_air_night", "units"), "media": ("sweep_tv_off", "tvs")},
    "away": {"lights": ("sweep_off", "lights"), "air": ("sweep_air_off", "units"), "media": ("sweep_tv_off", "tvs")},
    "home": {},
}

# the complementary pairs a refusal's blocker may be one side of (the agent's consult: what the person can change)
PAIRS = (("light_ok", "light_missing"), ("unit_ok", "unit_missing"), ("tv_ok", "tv_missing"),
         ("running", "stopped"), ("ir_ready", "ir_absent"))
WORDS = {"light_missing": "check that {X} has power and is in Home Assistant",
         "unit_missing": "check that {X} has power and is on the Wi-Fi",
         "tv_missing": "check that {X} is on the network and paired with Home Assistant",
         "stopped": "start {X} first",
         "ir_absent": "plug the infrared remote into the NUC"}


# ── the semantic world's levels (metis-lang spec/16 §4), as metis-home serves them ─────────────────────
# metis-home folds Home Assistant into the semantic world (metis-worlds libs/semantic-world/go, home
# adapter) and gives each package that declares beliefs:/levels: in its domain.yaml one level atom per
# key the world knows, every beat (none for a key it does not know). This host gives the same atoms from
# its simulated state, with the world's numbers in small: the belief per port below, quantised by the
# manifest's thresholds (names[#{t in at : t <= p}], no hysteresis). LEVELS is every manifest's levels:
# (a test holds them equal); PORTS are the ports semantic-world's home adapter offers (a manifest naming
# another fails metis-home's start, and a test here).
PORTS = ("present", "someone_home", "on", "reachable", "preset", "cold", "warm", "humid", "out_cold", "day")
LEVELS = {                         # level pred -> (port, at, names)
    "presence": ("present", (0.3, 0.7), ("nobody", "maybe_someone", "someone")),
    "power": ("on", (0.05, 0.95), ("off", "unconfirmed", "on")),
    "chill": ("cold", (0.5, 0.9), ("not_cold", "maybe_cold", "cold")),
    "heat": ("warm", (0.5, 0.9), ("not_warm", "maybe_warm", "warm")),
    "damp": ("humid", (0.5, 0.9), ("dry", "maybe_humid", "humid")),
    "outside": ("out_cold", (0.5,), ("mild_out", "cold_out")),
}
# the world's parameters (semantic-world home.DefaultParams), per second
L_MAX = 4.0                        # presence log-odds: sure (the radar's "someone"), and its floor
P_READ, P_CMD = 0.98, 0.9          # a device's power read back (reliability R) / predicted by a command
TEMP_R, TEMP_Q = 0.09, 0.0005      # a thermometer reading's variance (°C²), its growth while unheard (°C²/s)
RH_R, RH_Q = 4.0, 0.01             # the same for humidity (%²)
UNTRACK, RH_UNKNOWN = 1.5, 5.0     # sd beyond which a temperature / humidity is not known
OUT_SD = 0.5                       # an outside reading's sd (°C)
WARMUP = 3                         # beats a unit runs before its outside sensor reads the weather (metis-home: 120 s)


def quantise(p, at, names):
    return names[sum(1 for t in at if t <= p)]


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def load_map(path=MAP_PATH):
    m = json.loads(Path(path).read_text())
    return {k: v for k, v in m.items() if not k.startswith("_")}


def roles(m, section):
    return [k for k in m.get(section, {}) if not k.startswith("_")]


def _handle(args):
    return args.rstrip(")") if args else ""


def flips(atom):
    name, _, args = atom.partition("(")
    for a, b in PAIRS:
        if name in (a, b):
            return (b if name == a else a) + ("(" + args if args else "")
    return None


def words(atom, names=None):
    name, _, args = atom.partition("(")
    w, arg = WORDS.get(name), _handle(args)
    if w is None or arg in STANDING:
        return None
    return w.replace("{X}", (names or {}).get(arg, arg))


def key(atom, names=None):
    name, _, args = atom.partition("(")
    arg = _handle(args)
    if name not in WORDS or arg in STANDING:
        return None
    return (names or {}).get(arg, arg) if arg else "remote"


def hysteresis(prev, value, enter, leave, above):
    """A class with hysteresis: enter at `enter`, leave at `leave`; above: the class is value >= enter."""
    if value is None:
        return None
    if above:
        return value >= (leave if prev else enter)
    return value <= (leave if prev else enter)


# ── the backends: what the world is, and how a command reaches it ─────────────────────────────────────
class Sim:
    """The flat as a table in memory: every device answering, nothing sensed that is not wired."""
    name = "sim"

    def __init__(self, m):
        self.m = m
        self.lights = {l: {"lit": False, "ok": True} for l in roles(m, "lights")}
        self.units = {u: {"running": False, "preset": "normal", "heater": False, "winter": False, "ok": True,
                          "outside_c": None} for u in roles(m, "units")}
        self.tvs = {t: {"on": False, "ok": True} for t in roles(m, "tvs")}
        self.ir_ready = False
        self.presence = {r: None for r in roles(m, "rooms")}          # None: no radar in the room
        self.climate = {r: None for r in roles(m, "rooms")}           # None or {"c": .., "rh": ..}
        self.sun_up = True

    def read(self):
        return self

    def do(self, kind, role, op, value=None):
        dev = {"light": self.lights, "unit": self.units, "tv": self.tvs}[kind].get(role)
        if dev is None or not dev.get("ok", True):
            return False
        if kind == "light":
            dev["lit"] = op == "on"
        elif kind == "tv":
            if op in ("on", "off"):
                dev["on"] = op == "on"
        elif kind == "unit":
            if op in ("on", "off"):
                dev["running"] = op == "on"
                if op == "off":
                    dev["heater"] = False
            elif op == "preset":
                dev["preset"] = value
            elif op in ("heater", "winter"):
                dev[op] = bool(value)
        return True

    def ir(self, dev, key_):
        return self.ir_ready


class HA(Sim):
    """Home Assistant's REST API: all states in one read per beat (cached for the beat), a service call
    per command. The map's entities; an entity null is a device not in Home Assistant yet (not ok)."""
    name = "ha"

    def __init__(self, m, url, token, timeout=2.0):
        super().__init__(m)
        self.url, self.token, self.timeout = url.rstrip("/"), token, timeout
        self.at = 0.0

    def _call(self, method, path, body=None):
        req = urllib.request.Request(self.url + path, method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + self.token,
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.load(r)

    def _ent(self, kind, role):
        m = self.m
        if kind == "light":
            return m["lights"][role].get("entity")
        if kind == "tv":
            return m["tvs"][role].get("entity")
        return None

    def read(self):
        if time.time() - self.at < 0.8 * BEAT_S:
            return self
        try:
            st = {s["entity_id"]: s for s in self._call("GET", "/api/states")}
        except (urllib.error.URLError, OSError, ValueError) as e:
            print("  [home host] Home Assistant: %s" % e, file=sys.stderr)
            for d in list(self.lights.values()) + list(self.units.values()) + list(self.tvs.values()):
                d["ok"] = False
            return self
        self.at = time.time()
        bad = ("unavailable", "unknown", None)
        for l, d in self.lights.items():
            s = st.get(self.m["lights"][l].get("entity") or "")
            d["ok"] = bool(s) and s["state"] not in bad
            if d["ok"]:
                d["lit"] = s["state"] == "on"
        for t, d in self.tvs.items():
            s = st.get(self.m["tvs"][t].get("entity") or "")
            d["ok"] = bool(s) and s["state"] not in bad
            if d["ok"]:
                d["on"] = s["state"] not in ("off", "standby")
        for u, d in self.units.items():
            p = self.m["units"][u]["prefix"]
            sup, ext = st.get("fan.%s_supply_fan" % p), st.get("fan.%s_extract_fan" % p)
            d["ok"] = bool(sup and ext) and sup["state"] not in bad
            if not d["ok"]:
                continue
            d["running"] = "on" in (sup["state"], ext["state"])
            d["preset"] = sup["attributes"].get("preset_mode") or "normal"
            d["heater"] = (st.get("switch.%s_heater" % p) or {}).get("state") == "on"
            d["winter"] = (st.get("switch.%s_winter" % p) or {}).get("state") == "on"
            try:
                d["outside_c"] = float((st.get("sensor.%s_outside_temperature" % p) or {}).get("state"))
            except (TypeError, ValueError):
                d["outside_c"] = None
        for r in self.presence:
            e = (self.m.get("radar") or {}).get(r)
            self.presence[r] = None if not e else ("occupied" if (st.get(e) or {}).get("state") == "on" else "empty")
        for r in self.climate:
            e = (self.m.get("thermometers") or {}).get(r)
            if not e:
                self.climate[r] = None
                continue
            try:
                self.climate[r] = {"c": float(st[e["temperature"]]["state"]),
                                   "rh": float(st[e["humidity"]]["state"]) if e.get("humidity") else None}
            except (KeyError, TypeError, ValueError):
                self.climate[r] = None
        sun = st.get(self.m.get("sun") or "")
        self.sun_up = (sun or {}).get("state") != "below_horizon"
        self.ir_ready = False                                         # the IR remote: not yet wired
        return self

    def do(self, kind, role, op, value=None):
        try:
            if kind == "light" or kind == "tv":
                e = self._ent(kind, role)
                if not e:
                    return False
                dom = e.split(".")[0]
                svc = {"on": "turn_on", "off": "turn_off", "louder": "volume_up", "quieter": "volume_down"}[op]
                self._call("POST", "/api/services/%s/%s" % (dom, svc), {"entity_id": e})
            elif kind == "unit":
                p = self.m["units"][role]["prefix"]
                fans = ["fan.%s_supply_fan" % p, "fan.%s_extract_fan" % p]
                if op in ("on", "off"):
                    self._call("POST", "/api/services/fan/turn_%s" % op, {"entity_id": fans})
                elif op == "preset" and value in ("night", "boost"):
                    self._call("POST", "/api/services/fan/set_preset_mode", {"entity_id": fans, "preset_mode": value})
                elif op == "preset":            # normal: no preset. To verify on the unit: turn_on without a preset
                    self._call("POST", "/api/services/fan/turn_on", {"entity_id": fans})
                elif op in ("heater", "winter"):
                    self._call("POST", "/api/services/switch/turn_%s" % ("on" if value else "off"),
                               {"entity_id": "switch.%s_%s" % (p, op)})
            self.at = 0.0                                             # read again next beat
            return True
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            print("  [home host] %s %s %s: %s" % (kind, role, op, e), file=sys.stderr)
            return False

    def ir(self, dev, key_):
        return False                                                  # not yet wired


def backend(m):
    url = os.environ.get("METIS_HOME_HA")
    tok = Path(os.path.expanduser(os.environ.get("METIS_HOME_TOKEN") or "~/.config/fsttm/hass.token"))
    if url and tok.is_file():
        return HA(m, url, tok.read_text().strip())
    return Sim(m)


# ── the one world per process: the readings, the timers, the edges, the scene wishes ──────────────────
class World:
    def __init__(self, m=None, back=None):
        self.m = m or load_map()
        self.back = back or backend(self.m)
        self.th = self.m.get("thresholds") or {}
        self.queues = {p: [] for p in OUTCOMES}                       # per package: lines for its next tick
        self.since_empty = {}                                         # room -> beats empty (the vacant timer)
        self.prev = {}                                                # the last readings: the edges
        self.override = {}                                            # sim world lines: atom -> True
        self.commanded = {}                                           # unit -> (on?, the beat its grace ends): the world's prediction
        self.p_on = {}                                                # unit -> P(on) last believed (kept while it does not answer)
        self.run_beats = {}                                           # unit -> beats running (the outside sensor's warm-up)

    def _levels(self, r, pred, key, p):
        """The level atoms of PRED at KEY: exactly one true when the world knows p, none when p is None."""
        _, at, names = LEVELS[pred]
        lv = None if p is None else quantise(p, at, names)
        for n in names:
            r["%s(%s,%s)" % (pred, n, key)] = n == lv

    # the readings every package draws from, computed once per beat number
    def readings(self, beat):
        if self.prev.get("_beat") == beat:
            return self.prev["_r"]
        w = self.back.read()
        r, ev = {}, []
        for l, d in w.lights.items():
            r["light_lit(%s)" % l] = d["lit"]
            r["light_dark(%s)" % l] = not d["lit"]
            r["light_ok(%s)" % l] = d["ok"]
            r["light_missing(%s)" % l] = not d["ok"]
        for room in roles(self.m, "rooms"):
            lit = any(w.lights[l]["lit"] for l in w.lights if self.m["lights"][l]["room"] == room)
            r["room_lit(%s)" % room], r["room_unlit(%s)" % room] = lit, not lit
            pres = w.presence.get(room)
            if pres == "empty":
                self.since_empty[room] = self.since_empty.get(room, 0) + 1
            else:
                self.since_empty.pop(room, None)
            vacant_beats = (self.th.get("vacant_after_s") or [600])[0] / BEAT_S
            cls = ("unsensed" if pres is None else "occupied" if pres == "occupied"
                   else "vacant" if self.since_empty.get(room, 0) >= vacant_beats else "empty")
            for c in ("occupied", "empty", "vacant", "unsensed"):
                r["%s(%s)" % (c, room)] = c == cls
            if cls == "occupied" and self.prev.get("cls_%s" % room) not in (None, "occupied", "unsensed"):
                ev.append("entered(%s)" % room)
            self.prev["cls_%s" % room] = cls
            # the world's presence: sure on "someone", then down in log-odds while "nobody", to 0.3 at vacant_after_s
            vac_s = (self.th.get("vacant_after_s") or [600])[0]
            odds = (None if pres is None else L_MAX if pres == "occupied" else
                    max(-L_MAX, L_MAX - (L_MAX - math.log(0.3 / 0.7)) / vac_s * self.since_empty.get(room, 0) * BEAT_S))
            self._levels(r, "presence", room, None if odds is None else 1 / (1 + math.exp(-odds)))
            clim = w.climate.get(room)
            if clim:
                clim["age"] = clim.get("age", 0) + BEAT_S                 # s since its last reading: the spread grows
            sd = math.sqrt(TEMP_R + TEMP_Q * clim.get("age", 0)) if clim else None
            t = clim["c"] if clim and sd <= UNTRACK else None             # too old to know: untracked, no level
            th_cold, th_warm = self.th.get("room_cold_c", [19])[0], self.th.get("room_warm_c", [26])[0]
            self._levels(r, "chill", room, None if t is None else phi((th_cold - t) / sd))
            self._levels(r, "heat", room, None if t is None else 1 - phi((th_warm - t) / sd))
            cold = hysteresis(self.prev.get("cold_%s" % room), t, *self.th.get("room_cold_c", [19, 20]), above=False)
            warm = hysteresis(self.prev.get("warm_%s" % room), t, *self.th.get("room_warm_c", [26, 25]), above=True)
            tcls = "untracked" if t is None else "cold_room" if cold else "warm_room" if warm else "comfy_room"
            for c in ("cold_room", "comfy_room", "warm_room", "untracked"):
                r["%s(%s)" % (c, room)] = c == tcls
            for c, name in ((cold, "got_cold"), (warm, "got_warm")):
                key_ = "cold_%s" % room if name == "got_cold" else "warm_%s" % room
                if c and self.prev.get(key_) is False:
                    ev.append("%s(%s)" % (name, room))
                self.prev[key_] = c
            rh = clim.get("rh") if clim else None
            sd_rh = math.sqrt(RH_R + RH_Q * clim.get("age", 0)) if clim else None
            rh = rh if rh is not None and sd_rh <= RH_UNKNOWN else None
            self._levels(r, "damp", room, None if rh is None else 1 - phi((self.th.get("humid_pct", [65])[0] - rh) / sd_rh))
            humid =hysteresis(self.prev.get("humid_%s" % room), rh, *self.th.get("humid_pct", [65, 60]), above=True)
            hcls = "humidity_unknown" if rh is None else "humid_room" if humid else "fresh_room"
            for c in ("humid_room", "fresh_room", "humidity_unknown"):
                r["%s(%s)" % (c, room)] = c == hcls
            if humid and self.prev.get("humid_%s" % room) is False:
                ev.append("got_humid(%s)" % room)
            self.prev["humid_%s" % room] = humid
        rooms_sensed = [p for p in w.presence.values() if p is not None]
        home = None if not rooms_sensed else any(p == "occupied" for p in rooms_sensed)
        r["someone_home"], r["nobody_home"], r["home_unsensed"] = home is True, home is False, home is None
        if self.prev.get("home") is True and home is False:
            ev.append("left_home")
        if self.prev.get("home") is False and home is True:
            ev.append("came_home")
        self.prev["home"] = home
        r["day"], r["night"] = w.sun_up, not w.sun_up
        if w.sun_up and self.prev.get("sun") is False:
            ev.append("dawn")
        self.prev["sun"] = w.sun_up
        for u, d in w.units.items():
            for k, v in (("running", d["running"]), ("stopped", not d["running"]), ("heater_on", d["heater"]),
                         ("heater_off", not d["heater"]), ("winter_on", d["winter"]), ("winter_off", not d["winter"]),
                         ("unit_ok", d["ok"]), ("unit_missing", not d["ok"])):
                r["%s(%s)" % (k, u)] = v
            for p_ in ("normal", "night", "boost"):
                r["%s_mode(%s)" % (p_, u)] = d["preset"] == p_
            # the world's power: a reading believed (R), a command predicted until its grace ends, a unit
            # that does not answer kept at what was last believed
            cmd = self.commanded.get(u)
            p = ((P_CMD if cmd[0] else 1 - P_CMD) if cmd and beat <= cmd[1] else
                 (P_READ if d["running"] else 1 - P_READ) if d["ok"] else self.p_on.get(u, 0.5))
            self.p_on[u] = p
            self._levels(r, "power", u, p)
            # the outside sensor sits in the unit: with the fans stopped, or before they have run WARMUP
            # beats, it reads the unit, not the weather (the world drops those readings)
            self.run_beats[u] = self.run_beats.get(u, 0) + 1 if d["running"] else 0
            out = d["outside_c"] if d["running"] and self.run_beats[u] > WARMUP else None
            self._levels(r, "outside", u, None if out is None else
                         phi((self.th.get("outside_cold_c", [8])[0] - out) / OUT_SD))
            cold = hysteresis(self.prev.get("out_%s" % u), out, *self.th.get("outside_cold_c", [8, 10]), above=False)
            ocls = "out_unknown" if cold is None else "cold_out" if cold else "mild_out"
            for c in ("cold_out", "mild_out", "out_unknown"):
                r["%s(%s)" % (c, u)] = c == ocls
            if cold and self.prev.get("out_%s" % u) is False:
                ev.append("chilled(%s)" % u)
            self.prev["out_%s" % u] = cold
        for t, d in w.tvs.items():
            r["tv_on(%s)" % t], r["tv_off(%s)" % t] = d["on"], not d["on"]
            r["tv_ok(%s)" % t], r["tv_missing(%s)" % t] = d["ok"], not d["ok"]
        r["ir_ready"], r["ir_absent"] = w.ir_ready, not w.ir_ready
        for p, names in EVENTS.items():
            self.queues[p] += ["+" + e for e in ev if e.split("(")[0] in names]
        self.prev["_beat"], self.prev["_r"] = beat, r
        return r

    def fan_out(self, scene):
        for pkg, (pred, section) in SWEEPS.get(scene, {}).items():
            self.queues[pkg] += ["+%s(%s)" % (pred, role) for role in roles(self.m, section)]


_WORLD = [None]


def world():
    if _WORLD[0] is None:
        _WORLD[0] = World()
    return _WORLD[0]


def reset(m=None, back=None):
    """A fresh world (the tests; a new map)."""
    _WORLD[0] = World(m, back)
    return _WORLD[0]


# ── the per-package view ───────────────────────────────────────────────────────────────────────────
READS = {                          # per package: the reading preds it is kept in step with
    "lights": ("light_lit", "light_dark", "light_ok", "light_missing", "room_lit", "room_unlit",
               "occupied", "empty", "vacant", "unsensed", "day", "night", "presence"),
    "air": ("running", "stopped", "normal_mode", "night_mode", "boost_mode", "heater_on", "heater_off",
            "winter_on", "winter_off", "unit_ok", "unit_missing", "cold_out", "mild_out", "out_unknown",
            "power", "outside"),
    "media": ("tv_on", "tv_off", "tv_ok", "tv_missing", "ir_ready", "ir_absent"),
    "scenes": ("someone_home", "nobody_home", "home_unsensed", "day", "night"),
    "comfort": ("running", "stopped", "heater_on", "heater_off", "cold_room", "comfy_room", "warm_room",
                "untracked", "humid_room", "fresh_room", "humidity_unknown", "chill", "heat", "damp", "power"),
}
OWNED = {                          # beliefs the program switches: read back only after GRACE beats (a unit's
    "lights": ("light_lit", "light_dark", "room_lit", "room_unlit"),   # power is the world's: its level)
    "air": ("normal_mode", "night_mode", "boost_mode", "heater_on", "heater_off", "winter_on", "winter_off"),
    "media": ("tv_on", "tv_off"),
}
ACTS = {                           # a fired rule -> (kind, op, value): the name is the command
    "light_on": ("light", "on", None), "light_off": ("light", "off", None), "sweep_off": ("light", "off", None),
    "vacant_off": ("light", "off", None),
    "air_on": ("unit", "on", None), "air_off": ("unit", "off", None), "air_off_cold": ("unit", "off", None),
    "sweep_air_off": ("unit", "off", None), "sweep_air_off_heat": ("unit", "off", None),
    "air_night": ("unit", "preset", "night"), "air_night_from_boost": ("unit", "preset", "night"),
    "sweep_night": ("unit", "preset", "night"), "sweep_night_boost": ("unit", "preset", "night"),
    "air_boost": ("unit", "preset", "boost"), "air_boost_from_night": ("unit", "preset", "boost"),
    "normal_from_night": ("unit", "preset", "normal"), "normal_from_boost": ("unit", "preset", "normal"),
    "heater_up": ("unit", "heater", True), "heater_down": ("unit", "heater", False),
    "winter_up": ("unit", "winter", True), "winter_down": ("unit", "winter", False),
    "tv_up": ("tv", "on", None), "tv_down": ("tv", "off", None), "sweep_tv": ("tv", "off", None),
    "tv_louder": ("tv", "louder", None), "tv_quieter": ("tv", "quieter", None),
}


class View:
    script, last = {}, None        # no scripted day: the person and the world are live
    due = ()

    def __init__(self, pkg, case=None):
        self.pkg, self.beat = pkg, 0
        self.hold = {}             # role -> the beat its grace ends
        self.acted = ()            # (beat, rule, args): the actuation log

    @property
    def w(self):
        return world()

    def bind(self, reg):
        pass

    def ports(self):
        return {"backend": self.w.back.name, "package": self.pkg, "reads": list(READS[self.pkg])}

    def _corrections(self, counts):
        r = self.w.readings(self.beat)
        dos = []
        for atom, want in sorted(r.items()):
            pred, _, args = atom.partition("(")
            if pred not in READS[self.pkg]:
                continue
            role = _handle(args).split(",")[0] if args else ""
            if pred in OWNED.get(self.pkg, ()) and self.hold.get(role, 0) >= self.beat:
                continue
            want = self.w.override.get(atom, want)
            have = counts.get(atom, 0)
            if want and not have:
                dos.append("+" + atom)
            elif not want and have:
                dos.append("-%s %d" % (atom, have))
        return dos

    def tick(self, counts):
        self.beat += 1
        dos = ["-%s %d" % (a, n) for a, n in sorted(counts.items())
               if n and (a.split("(")[0] in OUTCOMES[self.pkg] or a.split("(")[0] in EVENTS[self.pkg]
                         or a.split("(")[0].startswith("sweep_"))]
        dos += self._corrections(counts)
        q = self.w.queues[self.pkg]
        dos += q
        self.w.queues[self.pkg] = []
        return dos

    def sync(self, counts):
        return self._corrections(counts)

    def on_event(self, name, args):
        base = name.split("[")[0].split("-")[0]
        self.acted += ((self.beat, base, tuple(args)),)
        if base in ("scene_set", "arrive"):
            scene = args[0] if args else "home"
            self.w.fan_out(scene if base == "scene_set" else "home")
            return
        if base == "ir_send" and len(args) >= 2:
            self.w.back.ir(args[0], args[1])
            return
        act = ACTS.get(base)
        if act:
            kind, op, value = act
            section = {"light": "lights", "unit": "units", "tv": "tvs"}[kind]
            role = next((x for x in args if x in self.w.m.get(section, {})), None)   # a rule's args are its variables, in its order
            if role is not None:
                self.w.back.do(kind, role, op, value)
                self.hold[role] = self.beat + GRACE
                if kind == "unit" and op in ("on", "off"):      # the world's prediction, unconfirmed for the grace
                    self.w.commanded[role] = (op == "on", self.beat + GRACE)

    def world(self, lines):
        """Driver lines on the simulated home (the tests, the page's World tab): a reading forced on
        (+atom) or off (-atom), or an event for the next beat (+entered(r1), +left_home, +dawn...).
        The real home takes none: its devices are the world."""
        if self.w.back.name != "sim":
            raise ValueError("the real home takes no world lines: change the device itself")
        evs = {e for es in EVENTS.values() for e in es}
        for line in lines:
            sign, atom = line[0], line[1:].split()[0]
            pred = atom.split("(")[0]
            if pred in evs:
                for p, names in EVENTS.items():
                    if pred in names:
                        self.w.queues[p].append("+" + atom)
                continue
            sim_world_line(self.w, sign, atom)

    def snapshot(self):
        return (self.beat, sorted(self.hold.items()), [list(a) for a in self.acted])

    def restore(self, snap):
        beat, hold, acted = snap
        self.beat, self.hold = beat, dict((k, v) for k, v in hold)
        self.acted = tuple((b, n, tuple(a)) for b, n, a in acted)


def sim_world_line(w, sign, atom):
    """A reading set in the simulated world itself (so every package sees it): a device's state, a
    room's presence or climate, the sun, the IR remote."""
    s = w.back
    pred, _, args = atom.partition("(")
    a = [x.strip() for x in _handle(args).split(",")] if args else []
    on = sign == "+"
    if pred in ("light_lit", "light_dark"):
        s.lights[a[0]]["lit"] = (pred == "light_lit") == on
    elif pred in ("light_ok", "light_missing"):
        s.lights[a[0]]["ok"] = (pred == "light_ok") == on
    elif pred in ("running", "stopped"):
        s.units[a[0]]["running"] = (pred == "running") == on
    elif pred in ("unit_ok", "unit_missing"):
        s.units[a[0]]["ok"] = (pred == "unit_ok") == on
    elif pred == "outside":                       # +outside(u1, 5): the unit's outside reading, °C
        s.units[a[0]]["outside_c"] = float(a[1]) if on else None
    elif pred in ("tv_on", "tv_off"):
        s.tvs[a[0]]["on"] = (pred == "tv_on") == on
    elif pred in ("tv_ok", "tv_missing"):
        s.tvs[a[0]]["ok"] = (pred == "tv_ok") == on
    elif pred in ("occupied", "empty"):          # +empty(r1, 400): empty for 400 s (the world's presence decaying)
        s.presence[a[0]] = pred if on else None
        if pred == "empty" and on and len(a) > 1:
            w.since_empty[a[0]] = int(float(a[1]) / BEAT_S) - 1
    elif pred == "vacant":                        # +vacant(r1): empty for longer than the timer (the tests' shortcut)
        s.presence[a[0]] = "empty" if on else None
        w.since_empty[a[0]] = 10 ** 9 if on else 0
    elif pred == "climate":                       # +climate(r1, 27, 50): °C and %RH
        s.climate[a[0]] = {"c": float(a[1]), "rh": float(a[2]) if len(a) > 2 else None, "age": 0} if on else None
    elif pred == "stale":                         # +stale(r1, 3000): the thermometer unheard for 3000 s
        s.climate[a[0]]["age"] = float(a[1])
    elif pred in ("day", "night"):
        s.sun_up = (pred == "day") == on
    elif pred in ("ir_ready", "ir_absent"):
        s.ir_ready = (pred == "ir_ready") == on
    else:
        raise ValueError("world line %r: not a reading the simulated home keeps" % atom)


def lights(case=None):
    return View("lights", case)


def air(case=None):
    return View("air", case)


def media(case=None):
    return View("media", case)


def scenes(case=None):
    return View("scenes", case)


def comfort(case=None):
    return View("comfort", case)


make = lights

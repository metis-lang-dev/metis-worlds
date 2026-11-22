"""The host: every family exactly one member per role, the timers and edges, the scene fan-out,
the grace after a command, and the Home Assistant mapping against a fake Home Assistant."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import home_host as hh

FAMILIES = [("light_lit", "light_dark"), ("light_ok", "light_missing"), ("room_lit", "room_unlit"),
            ("occupied", "empty", "vacant", "unsensed"), ("day", "night"), ("running", "stopped"),
            ("normal_mode", "night_mode", "boost_mode"), ("heater_on", "heater_off"), ("winter_on", "winter_off"),
            ("unit_ok", "unit_missing"), ("cold_out", "mild_out", "out_unknown"), ("tv_on", "tv_off"),
            ("tv_ok", "tv_missing"), ("ir_ready", "ir_absent"), ("someone_home", "nobody_home", "home_unsensed"),
            ("cold_room", "comfy_room", "warm_room", "untracked"), ("humid_room", "fresh_room", "humidity_unknown")]


def exactly_one(r):
    by_role = {}
    for atom, v in r.items():
        pred, _, args = atom.partition("(")
        for fam in FAMILIES:
            if pred in fam:
                by_role.setdefault((fam, args), []).append(v)
    return {k: sum(v) for k, v in by_role.items() if sum(v) != 1}


def test_families_exactly_one_member():
    w = hh.reset()
    w.back.presence["r1"], w.back.climate["r1"] = "occupied", {"c": 22.0, "rh": 50.0}
    w.back.units["u1"].update(running=True, outside_c=3.0)
    assert exactly_one(w.readings(1)) == {}


def test_vacant_after_the_timer_and_entered_edge():
    m = hh.load_map()
    m["thresholds"]["vacant_after_s"] = [3, 0]
    w = hh.reset(m)
    w.back.presence["r3"] = "empty"
    seen = [w.readings(b)["vacant(r3)"] for b in range(1, 6)]
    assert seen == [False, False, True, True, True]
    w.back.presence["r3"] = "occupied"
    w.readings(6)
    assert "+entered(r3)" in w.queues["lights"]


def test_outside_cold_has_hysteresis_and_reads_nothing_when_stopped():
    w = hh.reset()
    u = w.back.units["u2"]
    u.update(outside_c=2.0)
    assert w.readings(1)["out_unknown(u2)"]                       # stopped: the sensor reads the unit
    u.update(running=True, outside_c=12.0)
    warm = [w.readings(b) for b in range(2, 2 + hh.WARMUP)]         # the warm-up: the unit still reads itself
    assert all(r["out_unknown(u2)"] and not any(k.startswith("outside(") and v for k, v in r.items()) for r in warm)
    b0 = 2 + hh.WARMUP
    r = w.readings(b0)
    assert r["mild_out(u2)"] and r["outside(mild_out,u2)"]
    for i, (c, want, level) in enumerate(((9.0, "mild_out", "mild_out"), (7.5, "cold_out", "cold_out"),
                                          (9.5, "cold_out", "mild_out"), (10.5, "mild_out", "mild_out"))):
        u.update(outside_c=c)
        r = w.readings(b0 + 1 + i)
        assert r["%s(u2)" % want] and r["outside(%s,u2)" % level], (c, want, level)   # the level: no hysteresis
    assert w.queues["air"].count("+chilled(u2)") == 1


LEVEL_KEYS = {"presence": "rooms", "chill": "rooms", "heat": "rooms", "damp": "rooms", "power": "units",
              "outside": "units"}


def levels(r, pred, key):
    """The level atoms of PRED at KEY that hold (the world asserts at most one)."""
    return [a.split("(")[1].split(",")[0] for a, v in r.items() if v and a.startswith(pred + "(") and a.endswith("," + key + ")")]


def test_levels_at_most_one_per_key():
    w = hh.reset()
    w.back.presence["r1"], w.back.climate["r1"] = "occupied", {"c": 18.9, "rh": 66.0}
    w.back.units["u1"].update(running=True, outside_c=3.0)
    for b in range(1, 3 + hh.WARMUP):
        r = w.readings(b)
        for pred, section in LEVEL_KEYS.items():
            for key in hh.roles(w.m, section):
                assert len(levels(r, pred, key)) <= 1, (pred, key)
    assert levels(r, "presence", "r1") == ["someone"] and levels(r, "presence", "r2") == []   # no radar: no atom
    assert levels(r, "chill", "r1") == ["maybe_cold"] and levels(r, "heat", "r1") == ["not_warm"]  # borderline
    assert levels(r, "damp", "r1") == ["maybe_humid"] and levels(r, "chill", "r2") == []
    assert levels(r, "power", "u1") == ["on"] and levels(r, "power", "u2") == ["off"]
    assert levels(r, "outside", "u1") == ["cold_out"] and levels(r, "outside", "u2") == []


def test_presence_decays_to_nobody():
    m = hh.load_map()
    m["thresholds"]["vacant_after_s"] = [10, 0]
    w = hh.reset(m)
    w.back.presence["r3"] = "occupied"
    assert levels(w.readings(1), "presence", "r3") == ["someone"]
    w.back.presence["r3"] = "empty"
    seen = [levels(w.readings(b), "presence", "r3")[0] for b in range(2, 14)]
    assert seen[0] == "someone" and "maybe_someone" in seen and seen[-1] == "nobody"
    assert seen.index("nobody") >= 9                                  # not before vacant_after_s


def test_a_stale_thermometer_is_doubtful_then_untracked():
    w = hh.reset()
    w.back.climate["r1"] = {"c": 18.5, "rh": 50.0, "age": 0}
    r = w.readings(1)
    assert levels(r, "chill", "r1") == ["cold"] and r["cold_room(r1)"]
    w.back.climate["r1"]["age"] = 3000                                # unheard for 50 min: its spread has grown
    r = w.readings(2)
    assert levels(r, "chill", "r1") == ["maybe_cold"] and r["cold_room(r1)"]
    w.back.climate["r1"]["age"] = 5000                                # too old to know
    r = w.readings(3)
    assert levels(r, "chill", "r1") == [] and r["untracked(r1)"]


def test_a_commanded_unit_is_unconfirmed_for_the_grace():
    hh.reset()
    v = hh.air()
    v.tick({})
    v.on_event("air_on", ["u1"])
    seen = []
    for _ in range(hh.GRACE + 1):
        v.tick({})
        seen.append(levels(hh.world().readings(v.beat), "power", "u1"))
    assert seen == [["unconfirmed"]] * hh.GRACE + [["on"]]


def test_the_manifests_levels_are_the_hosts_and_name_the_worlds_ports():
    import yaml
    for pkg in ("lights", "air", "media", "scenes", "comfort"):
        d = yaml.safe_load((hh.HERE.parent / "domains" / pkg / "domain.yaml").read_text())
        for name, b in (d.get("beliefs") or {}).items():
            assert b["port"] in hh.PORTS, (pkg, name)
        for name, lv in (d.get("levels") or {}).items():
            port, at, names = hh.LEVELS[name]
            assert (lv["from"]["belief"], tuple(lv["at"]), tuple(lv["names"])) == (port, at, names), (pkg, name)
            assert lv["from"]["belief"] in {b["port"] for b in d["beliefs"].values()}, (pkg, name)
            assert name in hh.READS[pkg], (pkg, name)


def test_scene_fans_out_one_wish_per_device():
    w = hh.reset()
    hh.scenes().on_event("scene_set", ["night"])
    assert w.queues["lights"] == ["+sweep_off(l1)", "+sweep_off(l2)", "+sweep_off(l3)"]
    assert w.queues["air"] == ["+sweep_air_night(u1)", "+sweep_air_night(u2)"]
    assert w.queues["media"] == ["+sweep_tv_off(t1)"]


def test_a_switched_device_is_given_grace_then_corrected():
    hh.reset()
    v = hh.lights()
    v.tick({})
    v.on_event("light_on", ["l1"])                                # the sim obeys
    assert hh.world().back.lights["l1"]["lit"]
    hh.world().back.lights["l1"]["lit"] = False                     # ... then someone switches it off by hand
    counts = {"light_lit(l1)": 1, "light_ok(l1)": 1}
    held = [v.tick(counts) for _ in range(3)]
    assert not any("light_lit(l1)" in d for ds in held for d in ds)  # within the grace: no correction
    assert "-light_lit(l1) 1" in v.tick(counts)                      # after it: the surprise


def test_vacant_off_actuates_the_light_not_the_room():
    w = hh.reset()
    w.back.lights["l1"]["lit"] = True
    hh.lights().on_event("vacant_off[R=r3,L=l1]", ["r3", "l1"])
    assert not w.back.lights["l1"]["lit"]


class FakeHA:
    def __init__(self, states):
        self.states, self.calls = states, []
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, obj):
                b = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                assert self.headers["Authorization"] == "Bearer t0k"
                self._send(fake.states)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.calls.append((self.path, body))
                self._send([])

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]


def st(eid, state, **attrs):
    return {"entity_id": eid, "state": state, "attributes": attrs}


def test_home_assistant_mapping():
    fake = FakeHA([st("fan.lab_supply_fan", "on", preset_mode="night", percentage=30),
                   st("fan.lab_extract_fan", "on"), st("switch.lab_heater", "on"), st("switch.lab_winter", "off"),
                   st("sensor.lab_outside_temperature", "5.5"),
                   st("fan.bedroom_badriom_supply_fan", "off"), st("fan.bedroom_badriom_extract_fan", "off"),
                   st("sun.sun", "below_horizon")])
    m = hh.load_map()
    w = hh.reset(m, hh.HA(m, fake.url, "t0k"))
    r = w.readings(1)
    assert r["running(u2)"] and r["night_mode(u2)"] and r["heater_on(u2)"] and r["winter_off(u2)"]
    assert r["out_unknown(u2)"] and r["stopped(u1)"] and r["out_unknown(u1)"] and r["night"]   # u2: its warm-up
    assert levels(r, "power", "u2") == ["on"] and levels(r, "power", "u1") == ["off"]
    for b in range(2, 2 + hh.WARMUP):
        r = w.readings(b)
    assert r["cold_out(u2)"] and levels(r, "outside", "u2") == ["cold_out"]
    assert r["light_missing(l1)"] and r["tv_missing(t1)"] and r["unsensed(r1)"] and r["ir_absent"]
    assert exactly_one(r) == {}
    hh.air().on_event("air_boost_from_night", ["u2"])
    hh.air().on_event("heater_down", ["u2"])
    assert fake.calls == [
        ("/api/services/fan/set_preset_mode",
         {"entity_id": ["fan.lab_supply_fan", "fan.lab_extract_fan"], "preset_mode": "boost"}),
        ("/api/services/switch/turn_off", {"entity_id": "switch.lab_heater"})]
    fake.srv.shutdown()

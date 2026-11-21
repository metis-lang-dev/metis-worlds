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
    assert w.readings(2)["mild_out(u2)"]
    for b, c, want in ((3, 9.0, "mild_out"), (4, 7.5, "cold_out"), (5, 9.5, "cold_out"), (6, 10.5, "mild_out")):
        u.update(outside_c=c)
        assert w.readings(b)["%s(u2)" % want], (c, want)
    assert w.queues["air"].count("+chilled(u2)") == 1


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
    assert r["cold_out(u2)"] and r["stopped(u1)"] and r["out_unknown(u1)"] and r["night"]
    assert r["light_missing(l1)"] and r["tv_missing(t1)"] and r["unsensed(r1)"] and r["ir_absent"]
    assert exactly_one(r) == {}
    hh.air().on_event("air_boost_from_night", ["u2"])
    hh.air().on_event("heater_down", ["u2"])
    assert fake.calls == [
        ("/api/services/fan/set_preset_mode",
         {"entity_id": ["fan.lab_supply_fan", "fan.lab_extract_fan"], "preset_mode": "boost"}),
        ("/api/services/switch/turn_off", {"entity_id": "switch.lab_heater"})]
    fake.srv.shutdown()

"""cr_batch.py — the CommonRoad harvest (commonroad-world s-9b7591fb step 3b): every scenario of the index run once on
SUMO by the road tree, each host its own slice, no shared filesystem, one row per scenario and a surprise record per
failure. The commands, the layout, the row and the record: road/docs/harvest.md.

    road/tools/cr_batch.py plan --hosts taycann:12,panzer:28 [--set S] [--source S,S] [--ids ID,ID] [--limit N] [--host H]
    road/tools/cr_batch.py work [--host H] [--n K]
    road/tools/cr_batch.py launch --workers N [--host H] [--ssh USER@HOST]
    road/tools/cr_batch.py status [--host H] [--ssh USER@HOST]
    road/tools/cr_batch.py pull --ssh USER@HOST --host H
    road/tools/cr_batch.py recover [--host H]

Environment: METIS_AGENT_PY (../metis-agent/py/.venv/bin/python), METIS_HOME (../metis-catalog/domains/road),
SUMO_VENV (../.worlds/road: its bin, sumo and netconvert, first on PATH, and SUMO_HOME from it when unset),
COMMONROAD_ROOT (/bigdata/datasets/commonroad), COMMONROAD_CACHE (../.worlds/cr-cache: never under road/), COMMONROAD_HARVEST (/bigdata/work/harvest), CR_TICKS (1500),
CR_TIMEOUT (900 s), CR_STOP_AFTER_WINDOW (30: a run stops 30 s after its goal window's end, goal not reached)."""
import argparse
import hashlib
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROAD = Path(__file__).resolve().parents[1]
WORLDS = ROAD.parent
WS = WORLDS.parent
# the cache outside road/: metispy's catalog walk (metis.catalog.manifests.walk, ~10 a tick) reads every directory under
# road/, and a cache of thousands of scenario dirs there made a tick 1.6 s (164 s for 100 ticks, profiled, 2026-11-06)
CACHE = Path(os.environ.setdefault("COMMONROAD_CACHE", str(WS / ".worlds" / "cr-cache")))
HARVEST = Path(os.environ.get("COMMONROAD_HARVEST", "/bigdata/work/harvest"))
HOST = socket.gethostname().split(".")[0]
DIRS = ("queue", "running", "done", "rows", "records", "runs", "logs")


def pin():
    return (ROAD / "domains" / "catalog.pin").read_text().strip()[:7]


def worlds_commit():
    r = subprocess.run(["git", "-C", str(WORLDS), "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or None


def home(host=None):
    h = HARVEST / pin() / (host or HOST)
    for d in DIRS:
        (h / d).mkdir(parents=True, exist_ok=True)
    return h


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def write(p, obj):
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1) + "\n")
    tmp.replace(p)


def env():
    e = dict(os.environ)
    e.setdefault("METIS_HOME", str(WS / "metis-catalog" / "domains" / "road"))
    e.setdefault("COMMONROAD_ROOT", "/bigdata/datasets/commonroad")
    e.setdefault("COMMONROAD_CACHE", str(CACHE))
    venv = Path(os.environ.get("SUMO_VENV", str(WS / ".worlds" / "road")))
    if (venv / "bin").is_dir():                          # a host without apt sumo: the wheel's sumo and netconvert
        e["PATH"] = "%s:%s" % (venv / "bin", e.get("PATH", ""))
        if "SUMO_HOME" not in e:
            sh = sorted(venv.glob("lib/python3*/site-packages/sumo"))
            if sh:
                e["SUMO_HOME"] = str(sh[0])
    e["PYTHONUNBUFFERED"] = "1"
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):   # one core a worker: N workers, N cores
        e.setdefault(k, "1")
    return e


def agent_py():
    return os.environ.get("METIS_AGENT_PY", str(WS / "metis-agent" / "py" / ".venv" / "bin" / "python"))


def index_rows():
    p = CACHE / "index.json"
    if not p.exists():
        subprocess.run([str(ROAD / ".venv-cr" / "bin" / "python"), str(ROAD / "tools" / "cr_convert.py"), "--index"],
                       check=True, env=env())
    return sorted(json.loads(p.read_text())["rows"], key=lambda r: r["id"])


# ── plan: the same split on every host, by a hash of the id weighted by the hosts' numbers ──
def owner(sid, hosts):
    total = sum(w for _, w in hosts)
    x = int(hashlib.sha256(sid.encode()).hexdigest()[:8], 16) % total
    for h, w in hosts:
        if x < w:
            return h
        x -= w
    return hosts[-1][0]


def cmd_plan(a):
    hosts = [(h, int(w)) for h, w in (x.split(":") for x in a.hosts.split(","))]
    me = a.host or HOST
    rows = index_rows()
    n_index = len(rows)
    if a.ids:
        want = a.ids.split(",")
        rows = [r for r in rows if r["id"] in set(want)]
    if a.set:
        rows = [r for r in rows if r.get("set") == a.set]
    if a.source:
        rows = [r for r in rows if r.get("source") in set(a.source.split(","))]
    mine = [r for r in rows if owner(r["id"], hosts) == me]
    if a.limit:
        mine = mine[:a.limit]
    h = home(me)
    queued = skipped = 0
    for r in mine:
        sid = r["id"]
        if (h / "rows" / (sid + ".json")).exists() or (h / "running" / (sid + ".json")).exists() \
                or (h / "queue" / (sid + ".json")).exists():
            skipped += 1
            continue
        write(h / "queue" / (sid + ".json"), r)
        queued += 1
    plan = {"at": now(), "host": me, "hosts": hosts, "index": n_index, "selected": len(rows), "mine": len(mine),
            "queued": queued, "skipped": skipped, "args": {k: v for k, v in vars(a).items() if k != "func"},
            "pin": pin(), "worlds": worlds_commit()}
    plans = h / "plan.json"
    old = json.loads(plans.read_text()) if plans.exists() else []
    write(plans, (old if isinstance(old, list) else [old]) + [plan])
    print("plan %s: index %d, selected %d, this host's %d, queued %d, already there %d -> %s"
          % (me, n_index, len(rows), len(mine), queued, skipped, h))


# ── work: claim by rename, run, row, record ──
def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def cmd_recover(a, quiet=False):
    h = home(a.host)
    back = 0
    for job in sorted((h / "running").glob("*.json")):
        pidf = job.with_suffix(".pid")
        pid = int(pidf.read_text().split()[0]) if pidf.exists() else None
        if pid is None or not alive(pid):
            if (h / "rows" / job.name).exists():
                job.replace(h / "done" / job.name)
            else:
                job.replace(h / "queue" / job.name)
                back += 1
            pidf.unlink(missing_ok=True)
    if not quiet:
        print("recover %s: %d back to queue/" % (h.name, back))
    return back


def claim(h):
    jobs = sorted((h / "queue").glob("*.json"))
    random.shuffle(jobs)                                 # workers spread over the queue, not all at its head
    for job in jobs:
        dest = h / "running" / job.name
        try:
            os.rename(job, dest)
        except FileNotFoundError:
            continue                                     # another worker won it
        dest.with_suffix(".pid").write_text("%d %s\n" % (os.getpid(), HOST))
        return dest
    return None


def last_json(text):
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                pass
    return None


def error_kind(err, timed_out):
    if timed_out:
        return "timeout"
    if "cr_convert" in err or "netconvert" in err or "convert again" in err or "conversion" in err:
        return "convert"
    if "RuntimeError: cr" in err or "cr_world" in err:
        return "world"
    return "crash"


def last_line(err):
    """The exception's own line (a Python traceback's last `XError: ...`), else the last line."""
    lines = [l.strip() for l in err.splitlines() if l.strip()]
    exc = [l for l in lines if l.split(":")[0].endswith(("Error", "Exception", "Expired", "Interrupt"))]
    return (exc or lines or [""])[-1][:300]


def make_row(job, h, seed, started, wall, summ, err, rc, timed_out):
    row = {"id": job["id"], "set": job.get("set"), "source": job.get("source"), "country": job.get("country"),
           "tags": job.get("tags") or [], "host": HOST, "pin": pin(), "worlds": worlds_commit(), "seed": seed,
           "started": started, "ended": now(), "wall_s": round(wall, 1), "record_id": None, "error": None,
           "stopped": (summ or {}).get("stopped")}
    if summ is None:
        row.update(ticks=None, t=None, arrived=None, goal=None, contact=None, contacts=None, sumo_collisions=None,
                   off_lanelet=None, violations=None, rc=None, fired=[], untriggered=[], failed=[], summary=None,
                   error={"kind": error_kind(err, timed_out), "line": last_line(err), "rc": rc,
                          "trace": [l.rstrip() for l in err.splitlines() if l.strip()][-5:]})
        return row
    d = summ.get("director") or {}
    cr = d.get("cr") or {}
    reached = bool(cr.get("goal_reached"))
    goal = {"position_t": cr.get("goal_position_t"), "reached": reached, "window_s": cr.get("goal_window_s"),
            "window_ok": reached or (cr.get("goal_t") is not None)}
    contacts = cr.get("contacts") or []
    row.update(ticks=summ.get("ticks"), t=summ.get("t"), arrived=summ.get("arrived"), goal=goal,
               contact=bool(cr.get("contact")), contacts=len(contacts),
               sumo_collisions=summ.get("collision_events") or 0,
               off_lanelet={"ticks": cr.get("off_lanelet_ticks") or 0, "m": cr.get("off_lanelet_m") or 0.0},
               violations=summ.get("violations") or 0, rc=summ.get("rc"),
               fired=[t.get("id") if isinstance(t, dict) else t for t in d.get("triggered") or []],
               untriggered=list(d.get("unfired") or []), summary=summ)
    failed = []
    if row["contact"]:
        failed.append("contact")
    if row["sumo_collisions"]:
        failed.append("sumo_collision")
    if not reached:
        failed.append("goal")
    if row["off_lanelet"]["ticks"]:
        failed.append("off_lanelet")
    if row["violations"]:
        failed.append("violation")
    row["failed"] = failed
    if cr.get("errors"):
        row["cr_errors"] = cr["errors"]
    return row


MEMBER = {"contact": "responder", "sumo_collision": "responder", "goal": "planner", "off_lanelet": "planner",
          "violation": "road_director"}


def new_id():
    return time.strftime("%Y%m%dT%H%M%S") + "-%06x" % random.getrandbits(24)


def reading(row):
    f = row["failed"][0]
    g = row["goal"] or {}
    say = {"contact": "the ego's box touched a recorded obstacle's (%d intervals)" % row["contacts"],
           "sumo_collision": "SUMO reported %d collision events" % row["sumo_collisions"],
           "goal": "the goal was not reached (in the region at %s s, window %s)" % (g.get("position_t"), g.get("window_s")),
           "off_lanelet": "the ego left every lanelet for %d ticks (%.1f m)" % (row["off_lanelet"]["ticks"], row["off_lanelet"]["m"]),
           "violation": "the world counted %d violations" % row["violations"]}[f]
    return "cr:%s: %s, arrived %s at t %s." % (row["id"], say, row["arrived"], row["t"])


def trace_ks(tdir):
    """The trace's first and last k (seg-*.jsonl: a header line, then a line per tick with its k), or None."""
    ks = []
    for seg in sorted(tdir.glob("seg-*.jsonl")):
        with open(seg) as f:
            for line in f:
                if line.startswith('{"k":'):
                    try:
                        ks.append(json.loads(line)["k"])
                    except ValueError:
                        pass
    return (min(ks), max(ks)) if ks else None


def window(row, ks, dt=0.1):
    """record.window in trace ticks (nina, cr-harvest 2026-11-05): a contact's [first - 50, first]; the goal's [window
    end - 300, window end], or the run's end when it ends first or has no window; off-lanelet or a violation alone
    [first - 50, first] (a violation has no tick in the summary: the run's end). Clamped into the trace's ks."""
    cr = ((row.get("summary") or {}).get("director") or {}).get("cr") or {}
    end = int(round((row.get("t") or 0) / dt))
    f = row["failed"][0]
    ck = contact_ks(row, dt)
    if f == "contact" and ck["cr"] is not None:
        k1 = ck["cr"]; k0 = k1 - 50
    elif f == "sumo_collision" and (ck["sumo"] is not None or ck["cr"] is not None):
        k1 = ck["sumo"] if ck["sumo"] is not None else ck["cr"]; k0 = k1 - 50
    elif f == "goal":
        ends = [w[1] for w in (row["goal"] or {}).get("window_s") or [] if w]
        k1 = min(end, int(round(max(ends) / dt))) if ends else end
        k0 = k1 - 300
    elif f == "off_lanelet" and cr.get("off_lanelet_first_t") is not None:
        k1 = int(round(cr["off_lanelet_first_t"] / dt)); k0 = k1 - 50
    else:
        k1 = end; k0 = k1 - 300 if f == "sumo_collision" else k1 - 50
    if ks:
        k0, k1 = max(k0, ks[0]), min(max(k1, ks[0]), ks[1])
    k0 = min(max(0, k0), k1)
    return [k0, k1]


def contact_ks(row, dt=0.1):
    """Both first-contact ticks: CommonRoad's box test (director.cr.contacts) and SUMO's collision (collision_first); None
    where there is none."""
    s = row.get("summary") or {}
    cr = (s.get("director") or {}).get("cr") or {}
    first = s.get("collision_first") or {}
    return {"cr": int(round(cr["contacts"][0][0] / dt)) if cr.get("contacts") else None,
            "sumo": int(round(first["t"] / dt)) if first.get("t") is not None else None,
            "sumo_other": (first.get("victim") if first.get("collider") == "ego" else first.get("collider")) if first else None}


def make_record(row, h, run_dir):
    rid = new_id()
    while (h / "records" / (rid + ".json")).exists():
        rid = new_id()
    tr = run_dir / "trace"
    traces = sorted(p for p in tr.iterdir() if p.is_dir()) if tr.is_dir() else []
    rec = {"id": rid, "ts": now(), "who": "world", "status": "open", "member": MEMBER[row["failed"][0]],
           "reading": reading(row), "atoms": row["failed"], "scenario": "cr:" + row["id"], "row": "rows/%s.json" % row["id"]}
    if traces:
        rec["trace"] = "traces/" + traces[0].name
        rec["trace_path"] = "runs/%s/trace/%s" % (row["id"], traces[0].name)
        if (traces[0] / "config.yaml").exists():
            rec["config"] = rec["trace_path"] + "/config.yaml"
    rec["window"] = window(row, trace_ks(traces[0]) if traces else None)
    if set(row["failed"]) & {"contact", "sumo_collision"}:
        rec["contact_k"] = contact_ks(row)                     # both ticks, the architect's (4)
    write(h / "records" / (rid + ".json"), rec)
    return rid


def run_job(h, path, seed, ticks, timeout):
    job = json.loads(path.read_text())
    sid = job["id"]
    run_dir = h / "runs" / sid
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    cmd = [agent_py(), str(ROAD / "experiments" / "road_tree.py"), "cr:" + sid, str(seed), "--world", "sumo",
           "--ticks", str(ticks), "--out", str(run_dir), "--trace", str(run_dir / "trace"),
           "--stop-after-window", os.environ.get("CR_STOP_AFTER_WINDOW", "30")]
    started, t0 = now(), time.time()
    timed_out, rc = False, None
    try:
        p = subprocess.run(cmd, cwd=str(WORLDS), env=env(), capture_output=True, text=True, timeout=timeout)
        out, err, rc = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired as x:
        timed_out = True
        out = x.stdout.decode(errors="replace") if isinstance(x.stdout, bytes) else (x.stdout or "")
        err = x.stderr.decode(errors="replace") if isinstance(x.stderr, bytes) else (x.stderr or "")
    summ = last_json(out) if rc == 0 else None
    (run_dir / "stderr.txt").write_text(err[-20000:])
    row = make_row(job, h, seed, started, time.time() - t0, summ, err, rc, timed_out)
    if row["error"] is None and row["failed"]:
        row["record_id"] = make_record(row, h, run_dir)
    write(h / "rows" / (sid + ".json"), row)
    if row["error"] is None and not row["failed"]:
        shutil.rmtree(run_dir, ignore_errors=True)      # a pass keeps its row only
    path.replace(h / "done" / path.name)
    path.with_suffix(".pid").unlink(missing_ok=True)
    return row


def cmd_work(a):
    h = home(a.host)
    ticks = int(os.environ.get("CR_TICKS", 1500))
    timeout = int(os.environ.get("CR_TIMEOUT", 900))
    log = open(h / "logs" / ("worker-%s.log" % (a.n if a.n is not None else os.getpid())), "a", buffering=1)
    log.write("%s worker %d start, ticks %d, timeout %d s\n" % (now(), os.getpid(), ticks, timeout))
    n = 0
    while True:
        job = claim(h)
        if job is None:
            break
        try:
            row = run_job(h, job, a.seed, ticks, timeout)
            st = "error:%s" % row["error"]["kind"] if row["error"] else ("pass" if not row["failed"] else "fail:" + ",".join(row["failed"]))
            log.write("%s %s %s %.0fs\n" % (now(), row["id"], st, row["wall_s"]))
        except Exception as x:                          # the worker's own fault: the job goes back, the worker goes on
            log.write("%s %s worker-fault %r\n" % (now(), job.stem, x))
            if job.exists():
                job.replace(h / "queue" / job.name)
            job.with_suffix(".pid").unlink(missing_ok=True)
            time.sleep(5)
        n += 1
    log.write("%s worker %d done, %d jobs, queue empty\n" % (now(), os.getpid(), n))


# ── launch, status, pull ──
def remote(ssh, args):
    cmd = "cd %s && python3 road/tools/cr_batch.py %s" % (os.environ.get("CR_REMOTE_WORLDS", "~/repo/perotheia-packages/metis-worlds"),
                                                           " ".join(args))
    return subprocess.run(["ssh", "-o", "BatchMode=yes", ssh, cmd]).returncode


def cmd_launch(a):
    if a.ssh:
        sys.exit(remote(a.ssh, ["launch", "--workers", str(a.workers)] + (["--host", a.host] if a.host else [])))
    cmd_recover(a)
    me = a.host or HOST
    py = sys.executable
    for i in range(a.workers):
        unit = "cr-harvest-%s-%d" % (pin(), i)
        work = [py, str(Path(__file__).resolve()), "work", "--host", me, "--n", str(i), "--seed", str(a.seed)]
        sd = ["systemd-run", "--user", "--collect", "--unit", unit, "-p", "MemoryMax=6G", "-p", "Nice=10",
              "--working-directory", str(WORLDS)] + ["--setenv=%s=%s" % (k, os.environ[k]) for k in
              ("METIS_AGENT_PY", "METIS_HOME", "SUMO_VENV", "COMMONROAD_ROOT", "COMMONROAD_HARVEST", "CR_TICKS", "CR_TIMEOUT")
              if k in os.environ] + work
        r = subprocess.run(sd, capture_output=True, text=True)
        if r.returncode != 0:                           # no user systemd: nohup, nice, no memory cap (said)
            subprocess.Popen(["nohup", "nice", "-n", "10"] + work, cwd=str(WORLDS), start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=open(home(me) / "logs" / ("launch-%d.err" % i), "a"))
            print("worker %d: nohup (systemd-run failed: %s)" % (i, r.stderr.strip()[:120]))
        else:
            print("worker %d: %s" % (i, unit))


def counts(h):
    rows = [json.loads(p.read_text()) for p in (h / "rows").glob("*.json")]
    c = {"pass": 0, "fail": 0, "error": 0}
    walls = []
    for r in rows:
        c["error" if r["error"] else ("fail" if r["failed"] else "pass")] += 1
        walls.append(r["wall_s"])
    q = len(list((h / "queue").glob("*.json")))
    run = len(list((h / "running").glob("*.json")))
    pids = {p.read_text().split()[0] for p in (h / "running").glob("*.pid")}
    return rows, c, q, run, len(pids), walls


def cmd_status(a):
    if a.ssh:
        sys.exit(remote(a.ssh, ["status"] + (["--host", a.host] if a.host else [])))
    base = HARVEST / pin()
    hosts = [a.host] if a.host else sorted(p.name for p in base.iterdir() if p.is_dir()) if base.exists() else []
    for host in hosts:
        h = base / host
        rows, c, q, run, workers, walls = counts(h)
        done = len(rows)
        eta = "-"
        if walls and workers and q + run:
            med = sorted(walls)[len(walls) // 2]
            eta = "%.0f min" % ((q + run) * med / workers / 60)
        kinds = {}
        for r in rows:
            for f in (r["failed"] or []) + ([r["error"]["kind"]] if r["error"] else []):
                kinds[f] = kinds.get(f, 0) + 1
        print("%s pin %s: done %d (pass %d, fail %d, error %d), running %d, queued %d, workers %d, ETA %s; by measure %s"
              % (host, pin(), done, c["pass"], c["fail"], c["error"], run, q, workers, eta, kinds))


def cmd_pull(a):
    src = "%s:%s/" % (a.ssh, HARVEST / pin() / a.host)
    dest = HARVEST / pin() / a.host
    dest.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["rsync", "-a", "--include=rows/***", "--include=records/***", "--include=runs/***",
                        "--include=plan.json", "--include=logs/***", "--exclude=*", src, str(dest) + "/"])
    print("pull %s -> %s: rsync rc %d" % (src, dest, r.returncode))
    sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--hosts", required=True)
    for o in ("--set", "--source", "--ids", "--host"):
        p.add_argument(o)
    p.add_argument("--limit", type=int, default=0)
    w = sub.add_parser("work")
    w.add_argument("--host")
    w.add_argument("--n")
    w.add_argument("--seed", type=int, default=1)
    la = sub.add_parser("launch")
    la.add_argument("--workers", type=int, required=True)
    la.add_argument("--host")
    la.add_argument("--ssh")
    la.add_argument("--seed", type=int, default=1)
    s = sub.add_parser("status")
    s.add_argument("--host")
    s.add_argument("--ssh")
    pu = sub.add_parser("pull")
    pu.add_argument("--ssh", required=True)
    pu.add_argument("--host", required=True)
    r = sub.add_parser("recover")
    r.add_argument("--host")
    a = ap.parse_args()
    {"plan": cmd_plan, "work": cmd_work, "launch": cmd_launch, "status": cmd_status, "pull": cmd_pull,
     "recover": cmd_recover}[a.cmd](a)


if __name__ == "__main__":
    main()

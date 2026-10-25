"""mh_hier.py — MiniHack as a hierarchy of domains over roles (semantic-map s-d4270bed step 4, the user's
amendment: structured as ALFWorld's alf-hierarchy, not one flat base; semantic-world s-227b8e1b step 2: on the
library's grid map).

    task   the planner: the person's REACH (walk onto the goal) → goto(goal) to nav; reached(goal) → done
    nav    walks the host's route: one step toward its next cell a beat; on the stairs, reached(goal) (a frontier
           goal in view mode is no arrival: the host rebinds `goal` as the map grows); the next step a closed door →
           closed(p), a beast on it → guarded(p) (its refusals: the director detours)
    act    the one-cell actions: open(p) a door beside the robot → opened(p) (locked: kicked until it gives, then
           the cell steps: opened(p)); fight(p) a beast beside it → cleared(p) once the cell is free
    director  the lifted director (domains/director_domain.llp, metis-catalog's, byte-equal): closed(p) is
           answered by act's open(p), guarded(p) by act's fight(p), then nav gets its goal back (resume) — as
           ALFWorld's elsewhere(R) is answered by nav's goto(R) for access

The host owns the geometry (semantic_world.grid, libs/semantic-world: the map, the segment graph, the route with
gate costs over the known cells, the beasts predicted, the binding — stable — and next(p, d, q) between bound cells); the rules own the roles. Every domain is compiled
once over the capacity (no level in any source); a level is its map store and one shared NLE process.

    install(des_or_variant, root, view=False, k=K, seed=1) → {name: package dir} and ROOT/.run/config.yaml
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from semantic_world import grid  # noqa: E402  (libs/semantic-world, installed editable)

K = grid.K
SPECS = {
    "nav": dict(types=("cell", "beast"), goal="goto", out=("reached", "closed", "guarded"),
                dyn=("agent_at", "step", "door", "monster", "next", "toward", "stairs_down")),
    "act": dict(types=("cell", "beast"), goal="open", goals=("open", "fight"), out=("opened", "cleared"),
                dyn=("agent_at", "step", "door", "monster", "next", "said")),
    "task": dict(types=("cell",), goal="reach", takes=("reached", "opened", "cleared", "refused"), out=("goto", "done", "stuck"),
                 dyn=()),
}
NAMES = ("director", "task", "nav", "act")
DIRECTOR_OUT = ("wake", "sleep", "forward", "ask", "ended", "tick__grant", "tick__revoke")   # the last two: the tree director's
# the specialists' interface (specialist-tree s-404d001f step 2; metis-lang spec/15 §2.1): world readings are
# world-private (each session through its own binding), the goals and the results routed (in/out), the body the
# resource; the statuses their outs mean
STATUS = {"nav": {"success": ["reached"], "failure": []}, "act": {"success": ["opened", "cleared"], "failure": []},
          "task": {"success": ["done"], "failure": ["stuck"]}}
RESOURCES = ("motion",)
DIRECTOR_FIELDS = ("shared: {tick__status: in, tick__active: in, tick__done: in, tick__stuck: in, tick__want: in, tick__release: in, tick__grant: out, "
                   "tick__goal: out, tick__revoke: out, tick__cancel: out, tick__stop: in}\nresources: {motion: {count: 1, free: free, held_by: [holder]}}\n")
HOLD_GRANT, HOLD_STATUS = 1, 1     # brief §9 rule 4: a grant is not revoked within k ticks, a status holds m ticks


REPORTS = {"nav": ("tick__active", "tick__done"), "act": ("tick__active", "tick__done"),
           "task": ("tick__active", "tick__done", "tick__stuck")}     # the tree variant's own reports (the inversion)


def manifest_fields(spec, tree=False):
    """SPEC's manifest lines (spec/15 §2.1): shared {pred: in|out|resource|world-private}, status {success, failure};
    tree: its reports (the protocol's) are its outs too."""
    sp = SPECS[spec]
    shared = {p: "world-private" for p in sp["dyn"]}
    shared.update({g: "in" for g in (sp["goal"],) + tuple(sp.get("goals", ()))})
    shared.update({p: "in" for p in sp.get("takes", ())})
    shared.update({p: "out" for p in sp["out"]})
    if tree:
        shared.update({p: "out" for p in REPORTS[spec]})
        shared.update({p: "world-private" for p in TREE_DYN.get(spec, ())})
        if spec == "act":
            shared.update({"tick__want": "out", "tick__release": "out"})
        if spec != "task":
            shared["tick__grant"] = "in"       # gating: program — the director's grant is an in-copy its rules read
        shared["tick__cancel"] = "in"                             # the director's on a stop (step 3c): the task's too
    if spec != "task":
        shared["motion"] = "resource"
    return "shared: {%s}\nstatus: {success: [%s], failure: [%s]}\n%s" % (
        ", ".join("%s: %s" % kv for kv in shared.items()), ", ".join(STATUS[spec]["success"]), ", ".join(STATUS[spec]["failure"]),
        "gating: program\n" if tree and spec != "task" else "")


def composition():
    """The composition file (spec/15 §2.3; domains/hier/composition.yaml), alfworld's shape."""
    order = ["task", "nav", "act"]
    out = sorted({p for sp in SPECS.values() for p in sp["dyn"]} | {"reach"})
    cmds = ["goto", "open", "fight"]
    return ("# composition — MiniHack's hierarchy as one package (specialist-tree s-404d001f; generated by world/mh_hier.py)\n"
            "capacity: capacity.llp\nprotocol: iface/protocol_domain.llp\ninterfaces: [iface/minihack.llp]\nspecialists: [%s]\ndirect: director\n"
            "world: {out: [%s], in: [%s]}\n" % (", ".join(order), ", ".join(out + ["tick__stop"]), ", ".join(cmds)))   # tick__stop: the agent's on a stop (3c)


def hysteresis(k=HOLD_GRANT, m=HOLD_STATUS, ages=4):
    a = ["a%d" % i for i in range(ages)]
    return (["mature_grant(%s)" % x for x in a[k:]] + ["young_grant(%s)" % x for x in a[:k]]
            + ["mature_status(%s)" % x for x in a[m:]])


def _said():
    return " ".join(sorted({k for _, k in __import__("perceive").MESSAGES} | {"other"}))


def _head(name, what):
    return ["%% %s — %s (semantic-world s-227b8e1b step 2, world/mh_hier.py): over roles, the level the host's map." % (name, what),
            "catalog %s 1." % name, 'provenance text "%s" "2026-10-25".' % what, "layers (dyn).", "stages (act)."]


# the hierarchy's INTERFACE PACKAGE (specialist-tree s-404d001f step 3b; brief §11; spec/15 I10): every pred that
# crosses between the members, declared once — domains/hier/iface/minihack.llp, generated by tools/iface_gen.py from
# the interface check's cut (regenerate: `python3 tools/iface_gen.py <a tree install>/domains/hier/composition.yaml
# minihack --out minihack/domains/hier --write`); base() declares every pred locally, install strips the crossing
# ones into the include
IFACE = os.path.join(os.path.dirname(HERE), "domains", "hier", "iface")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools"))
import iface_gen  # noqa: E402
import protocol_stub  # noqa: E402


def crossing():
    """The family's crossing preds, from the committed interface package."""
    return set(iface_gen.declarations(open(os.path.join(IFACE, "minihack.llp")).read()))


# each member's own cases (metis.catalog.stub: the member alone, its interface closed with facts): the hierarchy's
# behaviours one member at a time, in roles; the tree variant fires its begin rule first and reports itself
def _cases(spec, tree):
    A = lambda d: ["tick__active(%s)" % d] if tree else []
    D = lambda d: ["tick__done(%s)" % d] if tree else []
    B = lambda *names: (["begin" + ("_" + names[0] if names and names[0] in ("open", "fight") else "")] if tree else [])
    if spec == "nav":
        return {
            "walk": {"case": "nav walks its route to the stairs", "boundaries": [
                {"world": ["agent_at(p1)", "next(p1, e, goal)", "toward(goal)", "step(goal)"], "deliver": ["goto(goal)"], "grant": ["motion"],
                 "expect": {"out": A("nav"), "status": "running", "fired": B() + ["move"]}},
                {"world": ["agent_at(goal)", "stairs_down(goal)"],
                 "expect": {"out": ["reached(goal)"] + D("nav"), "status": "success", "fired": ["arrive"]}}]},
            "door": {"case": "nav meets a closed door on its route and hands its goal back", "boundaries": [
                {"world": ["agent_at(p1)", "next(p1, e, p2)", "toward(p2)", "door(p2, closed)"], "deliver": ["goto(goal)"], "grant": ["motion"],
                 "expect": {"out": A("nav") + ["closed(p2)"], "status": "running", "fired": B() + ["shut"]}}]},
            **(_stop_cases("nav") if tree else {})}
    if spec == "act":
        return {
            "door": {"case": "act opens a closed door beside the robot", "boundaries": [
                {"world": ["agent_at(p1)", "next(p1, e, p2)", "door(p2, closed)"], "deliver": ["open(p2)"], "grant": ["motion"],
                 "expect": {"out": A("act"), "status": "running", "fired": B("open") + ["open_door"]}},
                {"world": ["agent_at(p1)", "next(p1, e, p2)", "door(p2, open)", "step(p2)"],
                 "expect": {"out": ["opened(p2)"] + D("act"), "status": "success", "fired": ["door_open"]}}]},
            "fight": {"case": "act fights a beast beside the robot until the way is clear", "boundaries": [
                {"world": ["agent_at(p1)", "next(p1, e, p2)", "monster(b1, p2)"], "deliver": ["fight(p2)"], "grant": ["motion"],
                 "expect": {"out": A("act"), "status": "running", "fired": B("fight") + ["move_fight"]}},
                {"world": ["agent_at(p1)", "next(p1, e, p2)", "step(p2)"],
                 "expect": {"out": ["cleared(p2)"] + D("act"), "status": "success", "fired": ["clear"]}}]},
            **({"guard": GUARD_CASE, "absorb": ABSORB_CASE} if tree else {}), **(_stop_cases("act") if tree else {})}
    if spec == "task":
        return {
            "reach": {"case": "task asks nav for the goal and is done when it is reached", "boundaries": [
                {"deliver": ["reach(goal)"], "expect": {"out": ["goto(goal)"] + A("task"), "status": "running", "fired": ["go"]}},
                {"deliver": ["reached(goal)"], "expect": {"out": ["done"] + D("task"), "status": "success", "fired": ["arrived"]}}]},
            "refused": {"case": "task stops when a refusal comes back that it has no rule for", "boundaries": [
                {"deliver": ["reach(goal)"], "expect": {"out": ["goto(goal)"] + A("task"), "status": "running", "fired": ["go"]}},
                {"deliver": ["refused(p3)"], "expect": {"out": ["stuck(p3)"] + (["tick__stuck(task)"] if tree else []),
                                                         "status": "failure", "fired": ["stuck_on"]}}]},
            **(_stop_cases("task") if tree else {})}
    return {}


def _stop_cases(spec):
    """A stop (step 3c, v8 §13.2): the director's tick__cancel(D) taken in — the member drops its goal (its generated
    cancel rules) and takes its next one as from idle."""
    if spec == "nav":
        return {"cancelled_mid_goal": {"case": "nav: a stop while it is on its goal", "boundaries": [
            {"deliver": ["goto(goal)"], "grant": ["motion"], "expect": {"out": ["tick__active(nav)"], "status": "running", "fired": ["begin"]}},
            {"deliver": ["tick__cancel(nav)"], "expect": {"out": [], "status": "running", "fired": ["cancel_goto"]}},
            {"deliver": ["goto(goal)"], "expect": {"out": ["tick__active(nav)"], "status": "running", "fired": ["begin"]}}]}}
    if spec == "act":
        return {"cancelled_mid_fight": {"case": "act: a stop while it fights", "boundaries": [
            {"world": ["agent_at(p1)", "next(p1, e, p2)", "monster(b1, p2)"], "deliver": ["fight(p2)"], "grant": ["motion"],
             "expect": {"out": ["tick__active(act)"], "status": "running", "fired": ["begin_fight", "move_fight"]}},
            {"deliver": ["tick__cancel(act)"], "expect": {"out": [], "status": "running", "fired": ["cancel_fighting_swung"]}},
            {"world": ["agent_at(p1)", "next(p1, e, p2)", "door(p2, closed)", "monster(b1, p2) 0"], "deliver": ["open(p2)"],
             "expect": {"out": ["tick__active(act)"], "status": "running", "fired": ["begin_open", "open_door"]}}]}}
    if spec == "task":
        go = {"deliver": ["reach(goal)"], "expect": {"out": ["goto(goal)", "tick__active(task)"], "status": "running", "fired": ["go"]}}
        return {"stop_mid_reach": {"case": "task: a stop on its way", "boundaries": [
            go, {"deliver": ["tick__cancel(task)"], "expect": {"out": [], "status": "running", "fired": ["cancel_want"]}}, go]}}
    return {}


def director_cases():
    """The tree director's own cases (step 3c): a stop cancels the members on the path and no idle one; a stop with
    nav queued behind act passes its ticket over (skipped), so a later want is granted."""
    # (the stub hands a boundary's outs over and retracts them; the Live's director keeps tick__goal, a level of its
    # own (I4): the second boundary puts it back as the Live's session holds it)
    return {"stop_cancels_the_path": {"case": "director: a stop cancels the path, not the idle", "boundaries": [
                {"deliver": ["tick__active(nav)"], "expect": {"out": ["tick__goal(nav)"], "fired": ["path_push"]}},
                {"lines": ["+tick__goal(nav) 1"], "deliver": ["tick__stop"], "expect": {"out": ["tick__cancel(nav)", "tick__cancel(task)"]}}]},
            "stop_after_stuck": {"case": "director: a stop after the task is stuck cancels nobody", "boundaries": [
                {"deliver": ["tick__stuck(task)"], "expect": {"out": [], "fired": ["path_stuck"]}},
                {"deliver": ["tick__stop"], "expect": {"out": []}}]},
            "stop_with_a_waiter": {"case": "director: a stop with nav queued behind act, then nav's want is granted", "boundaries": [
                {"deliver": ["tick__want(act, motion)"], "expect": {"out": ["tick__grant(act,motion)"]}},
                {"deliver": ["tick__want(nav, motion)"], "expect": {"out": []}},
                {"deliver": ["tick__stop"], "expect": {"out": ["tick__cancel(task)", "tick__revoke(act,motion)"]}},
                {"lines": ["-tick__stop 1"], "deliver": ["tick__want(nav, motion)"], "expect": {"out": ["tick__grant(nav,motion)"]}}]}}


def _granted(spec, cases):
    """gating: program (the tree): a boundary that grants motion delivers the director's grant too, the in-copy the
    member's rules read (the stub's `grant` alone is the holder flag)."""
    for c in cases.values():
        for b in c["boundaries"]:
            if "motion" in b.get("grant", ()):
                b["deliver"] = b.get("deliver", []) + ["tick__grant(%s, motion)" % spec]
    return cases


def write_cases(pkg, spec, tree=False):
    """SPEC's cases into PKG/cases/ (one YAML file a case)."""
    import yaml
    d = os.path.join(pkg, "cases")
    os.makedirs(d, exist_ok=True)
    cases = _cases(spec, tree)
    for name, c in (_granted(spec, cases) if tree and spec != "task" else cases).items():
        with open(os.path.join(d, name + ".yaml"), "w") as f:
            yaml.safe_dump(c, f, sort_keys=False, default_flow_style=None, width=200)


def _tree(on, plain, treed):
    """A rule's text, plain or in the tree variant (the inversion: the member reports itself)."""
    return treed if on else plain


# act's OWN trigger (specialist-tree s-404d001f step 3a, the beast case; steps/step3a-beast-brief.md): a beast the
# situation layer finds coming at the robot (the host's oncoming(B): opposite direction and dangerous, semantic_world
# .situation) wakes act by itself — it reports itself active and asks for the body (tick__want), which the director
# grants by priority over nav (preempt); it strikes when the beast is beside the robot, and gives the body back
# (tick__release, tick__done) once nothing is dangerous (the fold's resp_lon(none)). The director never calls it. The
# trigger reads a braking response (brakes(R)), so it and the stand-down never hold together. While the beast is not
# beside the robot (the host's closing(B), consumed: one wait a turn) act stands — the brake; the dungeon's turns pass
# only on a command.
GUARD = ["  %% {B} is coming at me: I take over.",
         "  guard [dyn] : $oncoming(B) * $resp_lon(R) * $brakes(R) * idle -o busy * alert(B) * tick__active(act) * tick__want(act, motion).",
         "  %% {B} is coming: I stand and let it come.",
         "  wait_for [dyn] : $alert(B) * $busy * $tick__grant(act, motion) * closing(B) -o braced(B).",
         "  %% {B} is beside me, {D}: I strike.",
         "  move_strike [dyn] : alert(B) * $busy * $tick__grant(act, motion) * $agent_at(C) * $next(C, D, P) * $monster(B, P) -o struck(B).",
         "  %% It still stands: again.",
         "  strike_on [dyn] : struck(B) * said(hit) * $monster(B, P) -o alert(B).",
         "  %% It is no danger now: the way is mine no more.",
         "  stand_down [dyn] : alert(B) * busy * $resp_lon(none) -o idle * tick__done(act) * tick__release(act, motion).",
         "  %% It is down: the way is clear.",
         "  struck_down [dyn] : struck(B) * busy * $resp_lon(none) -o idle * tick__done(act) * tick__release(act, motion).",
         "  %% I was asked to clear {P}: it is the beast I am on already.",
         "  absorb [dyn] : fight(P) * $alert(B) * $monster(B, P) -o owed(P).",
         "  %% I was asked to clear {P}: it is the beast I am on already.",
         "  absorb_struck [dyn] : fight(P) * $struck(B) * $monster(B, P) -o owed(P).",
         "  %% Nothing is coming any more: {P} is clear.",
         "  pay [dyn] : owed(P) * $resp_lon(none) -o cleared(P)."]
GUARD_DECLS = ["type resp {none brake_min_correct brake_min}.",
               "pred oncoming(beast) : act.              % the host's: the situation layer's opp_dir and dangerous, in roles",
               "pred resp_lon(resp) : act.               % the host's: the fold's response along the way",
               "pred brakes(resp) : act.                 % static: the responses that brake",
               "pred closing(beast) : act.               % the host's: oncoming and not beside yet",
               "pred alert(beast) : act.", "pred struck(beast) : act.", "pred braced(beast) : act.",
               "pred fighting : act.", "pred owed(cell) : act."]
GUARD_CASE = {"case": "a beast comes at the robot: act takes the body by itself, stands, strikes it beside, gives the body back",
              "boundaries": [
                  {"world": ["agent_at(p1)", "next(p1, e, p2)", "oncoming(b1)", "closing(b1)", "resp_lon(brake_min_correct)"],
                   "expect": {"out": ["tick__active(act)", "tick__want(act, motion)"], "status": "running", "fired": ["guard"]}},
                  {"world": ["agent_at(p1)", "next(p1, e, p2)", "oncoming(b1)", "closing(b1)", "resp_lon(brake_min_correct)"],
                   "grant": ["motion"], "expect": {"out": [], "status": "running", "fired": ["wait_for"]}},
                  {"world": ["agent_at(p1)", "next(p1, e, p2)", "monster(b1, p2)", "oncoming(b1)", "resp_lon(brake_min_correct)"],
                   "expect": {"out": [], "status": "running", "fired": ["move_strike"]}},
                  {"world": ["agent_at(p1)", "next(p1, e, p2)", "step(p2)", "resp_lon(none)"],
                   "expect": {"out": ["tick__done(act)", "tick__release(act, motion)"], "status": "running", "fired": ["struck_down"]}}]}
ABSORB_CASE = {"case": "act, already on a beast by itself, is asked to fight it too: it takes the request into its own, strikes once, "
                       "and answers it with cleared as well as its release",
               "boundaries": [
                   {"world": ["agent_at(p1)", "next(p1, e, p2)", "oncoming(b1)", "closing(b1)", "resp_lon(brake_min_correct)"],
                    "expect": {"out": ["tick__active(act)", "tick__want(act, motion)"], "status": "running", "fired": ["guard"]}},
                   {"world": ["agent_at(p1)", "next(p1, e, p2)", "monster(b1, p2)", "oncoming(b1)", "closing(b1) 0", "resp_lon(brake_min_correct)"],
                    "deliver": ["fight(p2)"], "expect": {"out": [], "status": "running", "fired": ["absorb"]}},
                   {"world": ["agent_at(p1)", "next(p1, e, p2)", "monster(b1, p2)", "oncoming(b1)", "resp_lon(brake_min_correct)"],
                    "grant": ["motion"], "expect": {"out": [], "status": "running", "fired": ["move_strike"]}},
                   {"world": ["agent_at(p1)", "next(p1, e, p2)", "step(p2)", "resp_lon(none)"],
                    "expect": {"out": ["cleared(p2)", "tick__done(act)", "tick__release(act, motion)"], "status": "success",
                               "fired": ["struck_down", "pay"]}}]}
TREE_DYN = {"act": ("oncoming", "closing", "resp_lon")}     # the tree variant's own readings (the beast case)


def base(spec, geometry="pred", tree=False):
    """SPEC's base (_base); the tree variant with its cancel rules after its begin rules (a stop, step 3c: generated
    by tools/protocol_stub.py from the member's own rules and goal kinds)."""
    t = _base(spec, geometry, tree)
    if not tree:
        return t
    sp = SPECS[spec]
    cancels = protocol_stub.cancel_rules(t, spec, [sp["goal"]] + list(sp.get("goals", ())),
                                         ends=STATUS[spec]["success"] + STATUS[spec]["failure"] if spec == "task" else (),
                                         decls=open(os.path.join(IFACE, "minihack.llp")).read())
    lines = t.split("\n")
    at = [k for k, l in enumerate(lines) if l.lstrip().startswith("begin") or l.strip() == "stage act {"]
    i = at[-1] if spec != "task" else at[0]
    return "\n".join(lines[:i + 1] + cancels + lines[i + 1:])


def _base(spec, geometry="pred", tree=False):
    """SPEC's lifted base over the capacity's types, every pred declared (install moves the crossing ones into
    the include: iface_gen.strip). geometry pred:
    next(p, d, q) is the host's projection's; bwd: a static table (a level's own cells: the flat comparison).
    tree (specialist-tree step 3b, the inversion): the member reports itself through the protocol — tick__active
    when it takes a goal (a per-goal idle → busy token, so it reports once and its work rules read $busy), tick__done
    with its result, tick__stuck with a failure; its instance includes the protocol."""
    geo = ("pred next(cell, dir, cell) : %s.        %% the host's: between bound cells, on the live session" % spec) if geometry == "pred" \
        else "bwd next(cell, dir, cell)."
    t = tree
    tok = ["pred idle : %s.                            %% the tree: no goal taken" % spec,
           "pred busy : %s.                            %% … a goal taken (reported active once)" % spec] if t else []
    if spec == "nav":
        return "\n".join(_head("nav_domain", "MiniHack's navigator: the host's path, one step a beat") + [
            "types (cell beast).", "type dir {n e s w ne se sw nw}.", "type doorstate {open closed}.", "namespace nav produce (dyn).",
            "pred agent_at(cell) : nav.", "pred step(cell) : nav.                     % the host's: the cell can be stepped on now (floor or an open door, no beast)",
            "pred door(cell, doorstate) : nav.", "pred monster(beast, cell) : nav.",
            "pred stairs_down(cell) : nav.              % the host's map: the stairs, under the robot too", geo,
            "pred toward(cell) : nav.                   % the host's: the next cell of its path",
            "pred goto(cell) : nav.", "pred reached(cell) : nav.", "pred closed(cell) : nav.", "pred guarded(cell) : nav."] + tok + [
            "stage act {"] + (["  %% I go for {G}.", "  begin [dyn] : $goto(G) * idle -o busy * tick__active(nav).   % reads its goal: re-putting it out would be a new arrival"] if t else []) + [
            "  %% I am on {G}.",
            _tree(t, "  arrive [dyn] : goto(G) * $agent_at(G) * $stairs_down(G) -o reached(G).   % a frontier goal is no arrival: the host rebinds it",
                  "  arrive [dyn] : goto(G) * busy * $agent_at(G) * $stairs_down(G) -o reached(G) * idle * tick__done(nav)."),
            "  %% I step {D}, to {P}.",
            _tree(t, "  move [dyn] : $goto(goal) * agent_at(C) * $next(C, D, P) * $toward(P) * $step(P) -o agent_at(P).   % only with its goal",
                  "  move [dyn] : $goto(goal) * $busy * $tick__grant(nav, motion) * agent_at(C) * $next(C, D, P) * $toward(P) * $step(P) -o agent_at(P)."),
            "  %% The door {D} is closed.",
            _tree(t, "  shut [dyn] : goto(goal) * $agent_at(C) * $next(C, D, P) * $toward(P) * $door(P, closed) -o closed(P).   % the host's goal: its route's end",
                  "  shut [dyn] : goto(goal) * busy * $tick__grant(nav, motion) * $agent_at(C) * $next(C, D, P) * $toward(P) * $door(P, closed) -o closed(P) * idle."),
            "  %% {B} is in my way, {D}.",
            _tree(t, "  in_way [dyn] : goto(goal) * $agent_at(C) * $next(C, D, P) * $toward(P) * $monster(B, P) -o guarded(P).",
                  "  in_way [dyn] : goto(goal) * busy * $tick__grant(nav, motion) * $agent_at(C) * $next(C, D, P) * $toward(P) * $monster(B, P) -o guarded(P) * idle."),
            "}", ""])
    if spec == "act":
        done = " * idle * tick__done(act)" if t else ""
        busy = " * busy" if t else ""
        rbusy = " * $busy" if t else ""
        grant = " * $tick__grant(act, motion)" if t else ""      # gating: program (specialist-tree 3a, the beast case)
        # the forwarded fight's own token (the tree): a fight act was asked for, not one it took up itself on its guard
        # (alert) — the two routes to one beast never both strike (the architect's ruling (b), the beast case)
        fight = " * fighting" if t else ""
        rfight = " * $fighting" if t else ""
        return "\n".join(_head("act_domain", "MiniHack's one-cell actions: a door, a beast beside the robot") + [
            "types (cell beast).", "type dir {n e s w ne se sw nw}.", "type doorstate {open closed}.",
            "type said_kind {%s}." % _said(), "namespace act produce (dyn).",
            "pred agent_at(cell) : act.", "pred step(cell) : act.", "pred door(cell, doorstate) : act.", "pred monster(beast, cell) : act.",
            "pred said(said_kind) : act.             % the world's message, one beat", geo,
            "pred open(cell) : act.", "pred fight(cell) : act.", "pred tried(cell) : act.", "pred kicked(cell) : act.", "pred swung(cell) : act.",
            "pred opened(cell) : act.", "pred cleared(cell) : act."] + tok + (GUARD_DECLS if t else []) + [
            "stage act {"] + (["  %% I see to {P}.", "  begin_open [dyn] : $open(P) * idle -o busy * tick__active(act).",
                               "  %% I take on {P}.", "  begin_fight [dyn] : $fight(P) * idle -o busy * fighting * tick__active(act)."] if t else []) + [
            "  %% The door {D} is closed: I open it.",
            "  open_door [dyn] : open(P)%s%s * $agent_at(C) * $next(C, D, P) * $door(P, closed) -o tried(P)." % (rbusy, grant),
            "  %% The door {D} is locked: I kick it.",
            "  kick_door [dyn] : tried(P) * said(door_locked)%s * $agent_at(C) * $next(C, D, P) * $door(P, closed) -o kicked(P)." % grant,
            "  %% It holds: I kick it again.",
            "  kick_on [dyn] : kicked(P) * said(whamm)%s * $agent_at(C) * $next(C, D, P) * $door(P, closed) -o kicked(P)." % grant,
            "  %% The door is broken: the way is open.",
            "  door_gone [dyn] : kicked(P)%s * $step(P) -o opened(P)%s." % (busy, done),
            "  %% The door is open.",
            "  door_open [dyn] : tried(P)%s * $door(P, open) -o opened(P)%s." % (busy, done),
            "  %% The door is already open.",
            "  was_open [dyn] : open(P)%s * $door(P, open) -o opened(P)%s." % (busy, done),
            "  %% {B} is in my way, {D}: I fight it.",
            "  move_fight [dyn] : fight(P)%s%s * $agent_at(C) * $next(C, D, P) * $monster(B, P) -o swung(P)." % (rbusy + rfight, grant),
            "  %% It still stands: again.",
            "  fight_on [dyn] : swung(P) * said(hit) * $monster(B, P) -o fight(P).",
            "  %% The way is clear.",
            "  clear [dyn] : swung(P)%s * $step(P) -o cleared(P)%s." % (busy + fight, done),
            "  %% The way is clear.",
            "  was_clear [dyn] : fight(P)%s * $step(P) -o cleared(P)%s." % (busy + fight, done),
            ] + (GUARD if t else []) + [
            "}", ""])
    if spec == "task":
        return "\n".join(_head("task_domain", "MiniHack's task: walk onto the goal, the specialists asked one goal at a time") + [
            "types (cell).", "namespace task produce (dyn).",
            "pred reach(cell) : task.                   % the one way in: the person's REACH",
            "pred want(cell) : task.", "pred goto(cell) : task.",
            "pred reached(cell) : task.", "pred opened(cell) : task.", "pred cleared(cell) : task.", "pred refused(cell) : task.",
            "pred done : task.", "pred stuck(cell) : task.",
            "stage act {",
            "  %% I'll walk onto {G}.",
            "  go [dyn] : reach(G) -o want(G) * goto(G)%s." % (" * tick__active(task)" if t else ""),
            "  %% I am on {G}: done.",
            "  arrived [dyn] : want(G) * reached(G) -o done%s." % (" * tick__done(task)" if t else ""),
            "  %% {X} was refused and I have no rule for it: I stop and ask.",
            "  stuck_on [dyn] : want(G) * refused(X) -o stuck(X)%s." % (" * tick__stuck(task)" if t else ""),
            "}", ""])
    raise ValueError(spec)


def committed(spec, tree=False):
    """SPEC's instance: the base and the capacity, no level (byte-equal for every level); tree: the protocol and the
    composition's types too (the specialist reads its grant from the protocol)."""
    return "\n".join(["% " + spec + " — MiniHack's " + spec + " over the role vocabulary (world/mh_hier.py): compiled once, the level the host's map.",
                      "catalog %s 1." % spec, 'provenance text "the %s specialist over roles" "2026-10-25".' % spec,
                      'include "../%s_domain.llp".' % spec, 'include "../capacity.llp".']
                     + (['include "iface/protocol_domain.llp".', 'include "../tick_types.llp".'] if tree else [])
                     + (["", "#init idle 1"] if tree and spec != "task" else [])
                     + (["#init brakes(brake_min) 1", "#init brakes(brake_min_correct) 1"] if tree and spec == "act" else []) + [""])


def kinds():
    out = {sp["goal"] for sp in SPECS.values()} | {g for sp in SPECS.values() for g in sp.get("goals", ())}
    return sorted(out | {k for sp in SPECS.values() for k in sp["out"]} | {k for sp in SPECS.values() for k in sp.get("takes", ())})


def director_facts():
    """The instance's facts (the lifted director's roles, as gen_hier.director_facts for ALFWorld)."""
    ks = kinds()
    f = ["specialist(nav)", "specialist(act)", "planner(task)", "handles(nav, goto)", "handles(act, open)", "handles(act, fight)",
         "handles(task, reach)"] + ["handles(task, %s)" % k for k in SPECS["task"]["takes"]]
    f += ["result(reached)", "result(opened)", "result(cleared)", "end(stuck)", "finished(done)"]
    f += ["detour(closed, open)", "detour(guarded, fight)", "escalate(closed, refused)", "escalate(guarded, refused)"]
    f += ["rename(closed, open, open)", "rename(guarded, fight, fight)", "rename(closed, refused, refused)", "rename(guarded, refused, refused)"]
    handled = {"goto", "open", "fight", "reach"} | set(SPECS["task"]["takes"])
    f += ["nohandler(%s)" % k for k in ks if k not in handled and k not in ("done", "stuck", "closed", "guarded")]
    return ks, f


def director_start(tree=False):
    out = ["active(task)", "attention(task)", "fresh", "inactive(nav)", "inactive(act)"]
    if tree:
        sp = [d for d in SPECS if d != "task"]
        out += ["free(%s)" % r for r in RESOURCES] + ["issue(%s,t0)" % r for r in RESOURCES] + ["serving(%s,t0)" % r for r in RESOURCES]
        out += ["path(task)", "tick__goal(task)"] + ["offpath(%s)" % d for d in sp]   # the planner on the path (its done pops it)
        out += ["nowant(%s)" % d for d in sp] + ["nolate(%s)" % d for d in sp] + ["age_of(%s,a0)" % d for d in SPECS]
    return out


TASK_CARD = """# task's intents (semantic-map step 4): what the person asks MiniHack's robot — one verb, REACH, whose atom is the
# task domain's goal reach(goal): the planner asks nav to walk there, the director detours a door to act. The goal is a
# role the host binds to the stairs down (or, while they are unseen, the nearest frontier cell).
persona: |
  You are a robot in a NetHack room. The person asks you to walk onto the goal (the stairs down). Map what
  they say to exactly one intent JSON per utterance. Respond with only the JSON.

verbs:
  - {verb: REACH, meaning: "walk onto the goal: the stairs down (standing on it wins)"}
  - {verb: CHITCHAT, meaning: "small talk, not an errand: an acknowledgement, thanks, a greeting, a comment"}
  - {verb: UNKNOWN, meaning: "anything else: one step on its own, an action you cannot do here"}

slots: {}

guidance: |
  Going to the stairs, the goal, the way down, the exit, or winning the level is REACH. Words that ask for no
  errand at all (okay, thanks, hello) are CHITCHAT.

examples:
  - ["walk onto the goal", {"intent":"REACH"}]
  - ["go to the stairs", {"intent":"REACH"}]
  - ["find the way down", {"intent":"REACH"}]
  - ["hello there", {"intent":"CHITCHAT"}]
  - ["step north", {"intent":"UNKNOWN"}]

spoken:
  heading: Spoken response (after the JSON)
  text: |
    After the JSON comes "Spoken response:" and one short sentence the robot says, in the first person.
    Never JSON, never an intent name.
  examples:
    - ["walk onto the goal", {"intent":"REACH"}, "I'll walk to the stairs."]
    - ["hello there", {"intent":"CHITCHAT"}, "Hello."]

map:
  - {verb: REACH, atom: "reach(goal)", act: reach}
values: {}

asks: []
outcomes: {goto: progress, done: done, stuck: refused}
alternatives:
  max: 0
  rules: {}
"""


def _director_base():
    """The lifted director: metis-catalog's domains/director/director_domain.llp (this world carries a byte copy,
    domains/director_domain.llp, as the alfworld world does)."""
    return open(os.path.join(os.path.dirname(HERE), "domains", "director_domain.llp")).read()


PRIORITY = (("act", "nav"),)      # the tree's strict order: act's own trigger (a beast coming) preempts nav's body


def install(level, root, view=False, k=K, seed=1, max_steps=600, name="level", tree=False, priority=None):
    """LEVEL (a des text, or a room variant tuple) installed for the agent under ROOT: ROOT/domains/hier/{director,
    task, nav, act} over the lifted bases and the capacity, the level's map store (.map.json), one shared NLE
    process for every host (the same level.json `shared` key), the task's card and ROOT/.run/config.yaml for
    metis-agent's service. → {name: package dir}."""
    import gen_level
    import levels
    from mh_gym import World
    from mh_host import ACTIONS
    des = level if isinstance(level, str) else levels.level(level, seed)["des"]
    w = World()
    try:
        info = w.open(des=des, actions=ACTIONS, max_steps=100, seed=seed)
    finally:
        if w.env is not None:
            w.env.close()
    hier = os.path.join(root, "domains", "hier")
    os.makedirs(hier, exist_ok=True)
    open(os.path.join(root, "domains", "director_domain.llp"), "w").write(_director_base())
    if tree:                                                   # the tick: the tree director, the protocol, the composition's types
        open(os.path.join(hier, "composition.yaml"), "w").write(composition())
        open(os.path.join(hier, "tick_types.llp"), "w").write(
            "%% tick_types — the composition's specialists and resources (specialist-tree step 2; world/mh_hier.py).\n"
            "catalog tick_types 1.\ntype domain {%s}.\ntype resource {%s}.\n" % (" ".join(NAMES[1:]), " ".join(RESOURCES)))
    os.makedirs(os.path.join(hier, "iface"), exist_ok=True)
    cross = set()                                              # no package yet (its first generation): every pred declared
    if os.path.exists(os.path.join(IFACE, "minihack.llp")):
        for f in ("minihack.llp", "minihack.yaml"):            # the family package, beside the bases
            shutil.copy(os.path.join(IFACE, f), os.path.join(hier, "iface", f))
        cross = crossing()
    for sp in SPECS:
        t = base(sp, tree=tree)
        open(os.path.join(hier, "%s_domain.llp" % sp), "w").write(iface_gen.strip(t, cross, "minihack") if cross else t)
    open(os.path.join(hier, "capacity.llp"), "w").write(grid.capacity(k))
    mp = os.path.abspath(os.path.join(hier, ".map.json"))
    grid.GridMap.build(mp, info["size"], des=des, view=view, k=k)
    shim = open(os.path.join(HERE, "package_host.py")).read().replace("__WORLD__", HERE)
    out = {}
    for sp in SPECS:
        pkg = os.path.join(hier, sp)
        os.makedirs(pkg, exist_ok=True)
        open(os.path.join(pkg, sp + ".llp"), "w").write(committed(sp, tree))
        json.dump({"des": des, "actions": ACTIONS, "seed": seed, "features": {"level": name}, "cells": info["cells"], "size": info["size"],
                   "map": mp, "max_steps": max_steps, "spec": sp, "shared": mp, "observe": list(SPECS[sp]["dyn"]) + (list(TREE_DYN.get(sp, ())) if tree else []),
                   "out": list(SPECS[sp]["out"]), "continues": True}, open(os.path.join(pkg, "level.json"), "w"), indent=1)
        open(os.path.join(pkg, "domain.yaml"), "w").write(
            "# %s — MiniHack's %s over the role program (generated by world/mh_hier.py).\n"
            "program: %s.llp\nhost: mh_host.py:make\nclock: {beats: 1}\nrecords: records/\n"
            "display: MiniHack %s\nline: \"the %s\"\nvoice: own\n" % (sp, sp, sp, sp, sp)
            + ("intent: {spec: intent.yaml}\n" if sp == "task" else "") + manifest_fields(sp, tree))
        write_cases(pkg, sp, tree)
        open(os.path.join(pkg, "mh_host.py"), "w").write(shim)
        out[sp] = pkg
    open(os.path.join(out["task"], "intent.yaml"), "w").write(TASK_CARD)
    _card_files(root, out["task"])
    out["director"] = _director_package(root, hier, mp, tree, priority=PRIORITY if priority is None and tree else priority or ())
    _config(root, tree)
    return out


def _card_files(root, task_dir):
    from pathlib import Path
    from metis import intents
    intents.ROOT = Path(root)
    spec, name = intents.load_from(task_dir), Path(task_dir).name
    d = Path(task_dir) / "intent"
    d.mkdir(exist_ok=True)
    for fn, text in [("%s.gbnf" % name, intents.grammar(spec)), ("%s-prompt.txt" % name, intents.prompt(spec)),
                     ("%s-spoken.txt" % name, intents.spoken(spec))]:
        (d / fn).write_text(text)


def _director_package(root, hier, mp, tree=False, priority=()):
    ks, facts = director_facts()
    pkg = os.path.join(hier, "director")
    os.makedirs(pkg, exist_ok=True)
    lines = ["% director — the director over MiniHack's hierarchy, installed for the agent (world/mh_hier.py).",
             "catalog director 1.", 'provenance text "generated: the director over nav/act/task" "2026-10-25".',
             'include "../../director_domain.llp".'] + (
            ['include "iface/director_tree_domain.llp".', 'include "iface/director_tree_wake.llp".']
            if tree else []) + [
             "type domain {%s}." % " ".join(SPECS), "type kind {%s}." % " ".join(ks), ""]
    lines += [f + "." for f in facts] + [""]
    if tree:
        lines += ["type resource {%s}." % " ".join(RESOURCES)] + [f + "." for f in hysteresis()]
        lines += ["priority(%s, %s)." % pq for pq in priority] + [""]      # who preempts whom (a strict order; opus's beast)
    lines += ["#init %s 1" % a for a in director_start(tree)] + ["#steps 6", "#seeds 1"]
    open(os.path.join(pkg, "director.llp"), "w").write("\n".join(lines) + "\n")
    json.dump({"root": root, "map": mp, "out": list(DIRECTOR_OUT), "kinds": ks, "specs": {s: {"dyn": list(v["dyn"]), "out": list(v["out"])}
                                                                                         for s, v in SPECS.items()}},
              open(os.path.join(pkg, "game.json"), "w"), indent=1)
    open(os.path.join(pkg, "domain.yaml"), "w").write(
        "# director — activation from context as a domain (world/mh_hier.py).\n"
        "program: director.llp\nhost: director_host.py:make\nclock: {beats: 1}\nrecords: records/\n"
        "display: the director\nline: \"the director: who is woken for what arrives\"\nvoice: line\n"
        + (DIRECTOR_FIELDS if tree else ""))
    shim = open(os.path.join(HERE, "package_host.py")).read().replace("__WORLD__", HERE).replace('"mh_host"', '"mh_director_host"') \
        .replace("MhHost", "DirectorHost")
    open(os.path.join(pkg, "director_host.py"), "w").write(shim)
    if tree:                                                       # its own cases (step 3c: the stop)
        import yaml
        os.makedirs(os.path.join(pkg, "cases"), exist_ok=True)
        for name, c in director_cases().items():
            with open(os.path.join(pkg, "cases", name + ".yaml"), "w") as f:
                yaml.safe_dump(c, f, sort_keys=False, default_flow_style=None, width=200)
    return pkg


def _config(root, tree=False):
    """metis-agent's service config over the hierarchy (the director, serve: active) — alfworld's shape."""
    import yaml
    run = os.path.join(root, ".run")
    os.makedirs(run, exist_ok=True)
    names = list(NAMES)
    c = {"model": "../go/models/gemma4/gemma-4-E2B-it-Q4_K_M.gguf", "template": "gemma4",
         "stop_words": ["stop", "halt", "freeze", "quiet"],
         "v3": {"prompt": ["../go/grammar/v3-orchestrator.txt"], "catalog": names, "loaded": ["director", "task"],
                "serve": "active", "director": "director", "n_ctx": 16384, "tick_ms": 300,
                "journal": os.path.join(run, "journal.jsonl")},
         "domains": {"names": names, "case": "live", "seed": 1, "clocks": [{"domain": n, "n": 1} for n in names],
                     "trace": True, "records": os.path.join(run, "records"), "narrator_n_ctx": 8192, "seat_n_ctx": 8192,
                     **({"tick": True} if tree else {})},
         "ws": {"addr": "127.0.0.1:8399"}}
    open(os.path.join(run, "config.yaml"), "w").write(yaml.safe_dump(c, sort_keys=False))

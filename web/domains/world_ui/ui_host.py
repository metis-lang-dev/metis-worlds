"""ui's host (console-nav s-b923ebfe): the page. A fired rule's event is an effect the page
carries out; the page reports back through the input port; observe() reads the page's real
state, so a focus change the port missed is the watch's surprise. README.md has the tables.

The effects (`effects`, the frames for the page; the agent's wire carries them, step 2):
  {"ui": "focus", "widget": W}          go_child go_named go_in_dialog exit exit_in_dialog exit_to_dialog home back
  {"ui": "show", "widget": W}           go_hidden (then the focus), show
  {"ui": "hide", "widget": W}           close (then the focus on the parent)
  {"ui": "numbers", "widget": W}        numbers: the focused list's entries 1–9
  {"ui": "unnumber"}                    every *_numbers rule (clear, blur, a dialog, a voice move, a jump, a cancel),
                                        and every rule that drops a pending choice unresolved (*_choice but
                                        pick_choice, pick_replace: the candidates' numbers go)
  {"ui": "jump"[, "letter": L]}          jump, jump_to: label the reachable widgets 1–9 (inside the dialog
                                        while one is up; with a letter, those whose name starts with it)
  {"ui": "jump_pick", "number": N}      jump_pick: resolve the label; the page answers +jumped(W) | +nothing_picked
  {"ui": "unjump"}                      clear_jump blur_jump open_jump go_/exit_/home_/back_jump cancel_jump
  focus (show first for jump_ok_hidden) jump_ok jump_ok_hidden jump_ok_dialog
  {"ui": "pick", "widget": W, "name"|"number": …[, "choice": true]}
                                        pick (the payload's name), pick_n (the number), pick_choice
  {"ui": "mode", "mode": M}             dictate command mode_back; hold_command hold_dictation (held: push-to-talk),
                                        release (the mode before the hold)
  {"ui": "activate"|"deactivate", "domain": "repl"}
                                        the focus entering or leaving the REPL's widgets (REPL_WIDGETS):
                                        the agent's card for it (brief item 15)
  move (the person's own focus) and the dialog's rise and fall are the page's: no effect.

The input port (the page's reports, port(report); the agent's world lines, world(lines)):
  {"focus": W}            focusin on W, mouse and keyboard alike; coalesced: one +enter(W)
                          per tick, the last one; none in a tick a dialog rose (its entry's
                          focusin is +opened(D)'s: one input, no race with dialog_open in sync)
  {"blur": true}          the focus left every widget: +blur
  {"opened": D} / {"closed": D}      a dialog rose / fell: +opened(D) / +closed(D)
  {"shown": W} / {"hidden": W}       the page showed / hid a dock itself: -hidden(W) +shown(W) …
  {"present": W} / {"absent": W}     the page has the widget now / has none (v6.5: the console's
                                     editor needs an open catalog): -absent(W) +present(W) …
  {"picked": true} / {"nothing_picked": true} / {"ambiguous": true}    a pick's answer
  {"jumped": W}           a jump label resolved to the widget W: +jumped(W) (a label that names
                          nothing: {"nothing_picked": true})
  {"page_refused": true}  the page declines a pick for its own reason (the navigator's own domain,
                          an inactive domain's atom, a tab the domain lacks): +page_refused
  {"sample": W | null}    ?focus(W) / ?blur: the page's real focus, sampled whenever it differs
                          from what the port said (a removed element, aria-activedescendant,
                          the viewport: the standards' silent cases). It asserts nothing: the
                          rules never see it; observe() reads it (the architect's H1)
The outcome tokens of the last pass are retracted at the tick, as dog_host does.

The sensor face: observe() is the page's real focused(W), shown(W)/hidden(W), present(W)/absent(W) and modal(D),
once the page has said anything and while no effect of ours waits for it (an effect the
page has not carried out yet is not a surprise; one it never carries out is, after
CATCH_UP beats). PURITY: the world changes only in tick/on_event/port; snapshot is total."""
import re

OUTCOMES = ("done", "refused", "progress")
UNJUMP = ("clear_jump", "blur_jump", "open_jump", "go_jump", "exit_jump", "home_jump", "back_jump", "cancel_jump")
WAITS = ()
REPL_WIDGETS = ("debugger", "stream", "lenses", "chips", "prompt")     # the REPL's widgets (ui.llp's tree)
CATCH_UP = 3                # beats the page has to carry out an effect before observe() reads it again
_BIND = re.compile(r"(\w+)=([^,\]]+)")


def _entries():
    """entry(D, E) facts of the instance beside this host (ui.llp)."""
    from pathlib import Path
    f = Path(__file__).resolve().parent / "ui.llp"
    return dict(re.findall(r"^entry\((\w+),\s*(\w+)\)\.", f.read_text(), re.M)) if f.is_file() else {}


def bindings(name):
    """go_child[W=catalog,F=root,Q=root] → {"W": "catalog", "F": "root", "Q": "root"}."""
    return dict(_BIND.findall(name.partition("[")[2]))


class UiHost:
    def __init__(self, case=None, entries=None):
        # where a dialog puts the focus when it rises (the instance's entry/2): the page folds that
        # focusin into +opened(D), so the host knows the page's focus from it
        self.entries = dict(entries) if entries is not None else _entries()
        self.beat, self.due, self.script, self.last = 0, (), {}, None     # AgentHost's hosted-day fields
        self.effects, self.lines, self.payload = [], [], {}
        self.acted = ()
        self.page = None            # the page's real state, once it reports: {focus, shown, hidden, modal}
        self.awaiting = None        # the beat by which the page should have carried out our last effect
        self.believed = "root"      # the focus the rules hold (for the card's activation)
        self.active = False         # the repl card is active
        self._focus_in = None       # the last focusin of this tick (coalesced)

    # -- the port --------------------------------------------------------------

    def _page(self):
        if self.page is None:
            self.page = {"focus": "root", "shown": set(), "hidden": set(), "modal": None}
        self.page.setdefault("present", set())
        self.page.setdefault("absent", set())
        return self.page

    def port(self, report):
        """One report of the page (a dict, the README's input port)."""
        p = self._page()
        if "focus" in report:
            p["focus"] = report["focus"]
            self._focus_in = report["focus"]
        elif report.get("blur"):
            p["focus"], self._focus_in = "root", None
            self.lines.append("+blur")
        elif "opened" in report:
            p["modal"] = report["opened"]
            p["focus"] = self.entries.get(report["opened"], report["opened"])     # the dialog takes the focus
            self.lines.append(f"+opened({report['opened']})")
        elif "closed" in report:
            p["modal"] = None
            self.lines.append(f"+closed({report['closed']})")
        elif "shown" in report:
            w = report["shown"]
            p["shown"].add(w)
            p["hidden"].discard(w)
            self.lines += [f"-hidden({w})", f"+shown({w})"]
        elif "hidden" in report:
            w = report["hidden"]
            p["hidden"].add(w)
            p["shown"].discard(w)
            self.lines += [f"-shown({w})", f"+hidden({w})"]
        elif "present" in report:
            w = report["present"]
            p["present"].add(w)
            p["absent"].discard(w)
            self.lines += [f"-absent({w})", f"+present({w})"]
        elif "absent" in report:
            w = report["absent"]
            p["absent"].add(w)
            p["present"].discard(w)
            self.lines += [f"-present({w})", f"+absent({w})"]
        elif "sample" in report:            # the page's real focus where the port said otherwise: no line
            p["focus"] = report["sample"] or "root"
        if "jumped" in report:
            self.lines.append(f"+jumped({report['jumped']})")
        for k in ("picked", "nothing_picked", "ambiguous", "page_refused"):
            if report.get(k):
                self.lines.append("+" + k)
        if "focus" in report and self.awaiting is not None and report["focus"] == self.believed:
            self.awaiting = None            # the page carried out our focus effect

    def world(self, lines):
        """The agent's world lines, as the page sends them (+enter(W), +blur, +opened(D), …)."""
        for l in lines:
            s = re.match(r"^\?(focus)\((\w+)\)$|^\?(blur)$", l)
            if s:                               # a sample: the page's real focus, asserting nothing
                self.port({"sample": s.group(2) if s.group(1) else None})
                continue
            m = re.match(r"^\+(\w+)(?:\((\w+)\))?$", l)
            if m and m.group(1) == "enter":
                self.port({"focus": m.group(2)})
            elif m and m.group(1) in ("opened", "closed", "shown", "hidden", "present", "absent", "jumped"):
                self.port({m.group(1): m.group(2)})
            elif m and m.group(1) in ("blur", "picked", "nothing_picked", "ambiguous", "page_refused"):
                self.port({m.group(1): True})
            elif not l.startswith("-"):
                raise ValueError(f"world line {l!r}: the ui port takes +enter(W) +blur +opened(D) +closed(D) "
                                 "+shown(W) +hidden(W) +present(W) +absent(W) +picked +nothing_picked +ambiguous +page_refused +jumped(W) ?focus(W) ?blur")

    def take_payload(self, payload):
        self.payload = dict(payload or {})

    # -- the plugin faces --------------------------------------------------------

    def bind(self, reg):
        pass

    def tick(self, counts):
        if self.last is not None and self.beat >= self.last:
            return None
        self.beat += 1
        dos = [f"-{a} {n}" for a, n in sorted(counts.items()) if n and a.split("(")[0] in OUTCOMES]
        if any(l.startswith("+opened(") for l in self.lines):
            self._focus_in = None               # the dialog's rise focuses its entry: that is +opened's, not a move
        if self._focus_in is not None:          # coalesced: the last focusin of the tick, once
            dos.append(f"+enter({self._focus_in})")
            self._focus_in = None
        dos += self.lines
        self.lines = []
        if self.awaiting is not None and self.beat > self.awaiting:
            self.awaiting = None                # the page had its time: observe() reads it again
        return dos + self.script.get(self.beat, [])

    def _effect(self, e):
        self.effects.append(e)
        if e["ui"] in ("focus", "show", "hide"):
            self.awaiting = self.beat + CATCH_UP
        if self.page is not None and e["ui"] in ("show", "hide"):
            # the page carries a dock's show or hide out without reporting it (the port reports only
            # what it does by itself), so its model takes the state it will be in (nina's H4)
            w, (add, drop) = e["widget"], (("shown", "hidden") if e["ui"] == "show" else ("hidden", "shown"))
            self.page[add].add(w)
            self.page[drop].discard(w)

    def _focus(self, w):
        self.believed = w
        self._effect({"ui": "focus", "widget": w})

    def _activation(self):
        inside = self.believed in REPL_WIDGETS
        if inside != self.active:
            self.active = inside
            self.effects.append({"ui": "activate" if inside else "deactivate", "domain": "repl"})

    def on_event(self, name, args):
        base, b = name.split("[")[0], bindings(name)
        p, self.payload = self.payload, {}
        if base in ("go_child", "go_named", "go_in_dialog"):
            self._focus(b["W"])
        elif base == "go_hidden":
            self._effect({"ui": "show", "widget": b["W"]})
            self._focus(b["W"])
        elif base in ("exit", "exit_in_dialog", "back"):
            self._focus(b["P"])
        elif base == "exit_to_dialog":          # from a direct child of the dialog: onto the dialog itself
            self._focus(b["D"])
        elif base == "home":
            self._focus("root")
        elif base == "move":
            self.believed = b["N"]              # the person's own focus: nothing to do on the page
        elif base == "blur_root":
            self.believed = "root"
        elif base == "dialog_open":
            self.believed = b.get("E", self.believed)
        elif base == "dialog_close":
            self.believed = b.get("W", self.believed)
        elif base == "show":
            self._effect({"ui": "show", "widget": b["W"]})
        elif base == "close":
            self._effect({"ui": "hide", "widget": b["W"]})
            self._focus(b["P"])
        elif base == "numbers":
            self._effect({"ui": "numbers", "widget": b["W"]})
        elif base.endswith("_numbers") and not base.startswith("p_"):
            self._effect({"ui": "unnumber"})    # any move, a dialog, a jump, a cancel: the numbers go
        elif (base.endswith("_choice") and base != "pick_choice" and not base.startswith("p_")) or base == "pick_replace":
            # a pending choice dropped unresolved: the page's numbered candidates go (nina's H3);
            # pick_choice resolves it, and the page clears them itself when it answers
            self._effect({"ui": "unnumber"})
            if base == "pick_replace":
                self._effect({"ui": "pick", "widget": b.get("W", self.believed), "name": str(p.get("name") or "")})
        elif base in UNJUMP:
            self._effect({"ui": "unjump"})      # the labels go
        elif base == "jump":
            self._effect({"ui": "jump"})
        elif base == "jump_to":
            self._effect({"ui": "jump", "letter": b["L"]})
        elif base == "jump_pick":
            self._effect({"ui": "jump_pick", "number": int(b["N"][1:])})
        elif base in ("jump_ok", "jump_ok_dialog"):
            self._focus(b["W"])
        elif base == "jump_ok_hidden":
            self._effect({"ui": "show", "widget": b["W"]})
            self._focus(b["W"])
        elif base == "pick":
            self._effect({"ui": "pick", "widget": b["W"], "name": str(p.get("name") or "")})
        elif base == "pick_n":
            self._effect({"ui": "pick", "widget": b["W"], "number": int(b["N"][1:])})
        elif base == "pick_choice":
            self._effect({"ui": "pick", "widget": self.believed, "number": int(b["N"][1:]), "choice": True})
        elif base in ("dictate", "command", "mode_back"):
            self._effect({"ui": "mode", "mode": "dictation" if base == "dictate" else "command"})
        elif base in ("hold_command", "hold_dictation"):
            self._effect({"ui": "mode", "mode": "held"})          # push-to-talk: the band says the page's channel has the voice
        elif base == "release":
            self._effect({"ui": "mode", "mode": b["M"]})          # the mode before the hold, back
        self._activation()
        self.acted += ((self.beat, name),)

    def observe(self, counts):
        if self.page is None or self.awaiting is not None or self.lines or self._focus_in is not None:
            return {}               # the page has said nothing yet, or has an effect or a report in flight
        p = self.page
        widgets = {a[8:-1] for a in counts if a.startswith("focused(")} | {p["focus"]}
        out = {f"focused({w})": 1 if w == p["focus"] else 0 for w in widgets}
        for w in p["shown"]:
            out[f"shown({w})"], out[f"hidden({w})"] = 1, 0
        for w in p["hidden"]:
            out[f"shown({w})"], out[f"hidden({w})"] = 0, 1
        for w in p.get("present", ()):
            out[f"present({w})"], out[f"absent({w})"] = 1, 0
        for w in p.get("absent", ()):
            out[f"present({w})"], out[f"absent({w})"] = 0, 1
        modal = {a[6:-1] for a in counts if a.startswith("modal(")}
        for d in modal | ({p["modal"]} if p["modal"] else set()):
            out[f"modal({d})"] = 1 if d == p["modal"] else 0
        return out

    def snapshot(self):
        p = self.page
        return [self.beat, list(self.due), [list(a) for a in self.acted], self.believed, self.active, self.awaiting,
                list(self.lines), self._focus_in,
                None if p is None else {"focus": p["focus"], "shown": sorted(p["shown"]),
                                        "hidden": sorted(p["hidden"]), "modal": p["modal"],
                                        "present": sorted(p.get("present", ())), "absent": sorted(p.get("absent", ()))}]

    def restore(self, snap):
        beat, due, acted, self.believed, self.active, self.awaiting, lines, self._focus_in, p = snap
        self.beat, self.due = beat, tuple((b, d) for b, d in due)
        self.acted, self.lines = tuple((b, n) for b, n in acted), list(lines)
        self.page = None if p is None else {"focus": p["focus"], "shown": set(p["shown"]),
                                            "hidden": set(p["hidden"]), "modal": p["modal"],
                                            "present": set(p.get("present", ())), "absent": set(p.get("absent", ()))}


def make(case):
    return UiHost(case)

"""perceive.py — NLE's observation as the program's atoms (world-minihack step 1).

The map (glyphs + chars) becomes atoms over CELLS (`c3_2`: column 3, row 2 of the level's
own map, not the 79×21 screen): `agent_at(C)`, `floor(C)`, `wall(C)`, `door(C, open|closed)`,
`stairs_down(C)`, `obj(NAME, C)` (NLE's object name), `monster(NAME, C)`, `trap(KIND, C)`
(once seen), `peaceful(NAME, C)` for a monster the screen calls peaceful (farlook's words, NLE's
screen_descriptions: no turn spent; nav-belief-2 (b)); the bottom line becomes `hp(N)`, `hpmax(N)`, `hunger(STATE)`, `turn(N)`; the
inventory `holds(NAME)` per item class word; the message line becomes EVENTS the host
hands in as atoms for one beat: `said(KIND)` with KIND from a small table of NetHack's
messages (solid stone, you see here, you kill, it bites, you fall into a pit, there is a
closed door, you eat, you pick up, …), `said(other)` for the rest, and the words kept
beside for the record.
"""
import re
import numpy as np
from nle import nethack
# NetHack 3.6 cmap indices (rm.h; nle does not export the S_* names): doorway, open v/h door, closed v/h door
S_NDOOR, DOORS_OPEN, DOORS_CLOSED = 12, {13, 14}, {15, 16}


HUNGER = {0: "satiated", 1: "normal", 2: "hungry", 3: "weak", 4: "fainting", 5: "fainted", 6: "starved"}

MESSAGES = [
    (r"solid stone", "blocked"), (r"you see here (an? |the )?(.+?)\.", "see_here"), (r"there is (an? )?(open|closed|broken) door", "door_here"),
    (r"the door is closed", "door_closed"), (r"the door opens", "door_opened"), (r"this door is locked", "door_locked"), (r"whamm", "whamm"), (r"you succeed in unlocking", "unlocked"), (r"you don't have anything to use", "nothing_to_apply"),
    (r"you kill (the )?(.+?)!", "killed"), (r"you (hit|miss) (the )?(.+?)[.!]", "hit"), (r"(bites|hits|kicks|stings)!?", "hurt"),
    (r"you fall into a pit", "fell_pit"), (r"a trap door opens", "trap_door"), (r"you (eat|finish eating)", "ate"),
    (r"(\w) - (.+?)\.", "picked"), (r"there is nothing here to pick up", "nothing_here"), (r"you can.?t (go|move) ", "cant"),
    (r"you are (hungry|weak|fainting)", "hunger"), (r"you die", "died"), (r"welcome", "welcome"), (r"it.s a wall", "blocked"),
    (r"you cannot pass", "blocked"), (r"you stop\.", "stopped"), (r"never mind", "nevermind"), (r"what do you want", "prompt"),
    (r"\[yn[aq]*\]", "asked"),          # a y/n question: the gym answers it "n" (mh_gym.World.answered; nav-belief-2 (c))
]


def cell(x, y):
    return "c%d_%d" % (x, y)


class Perceiver:
    """Fixed per level: the map's bounding box on the screen (so cells are level coordinates)."""

    def __init__(self, chars, size=None, start=None):
        """The level's bounding box: its top-left from the first screen (the agent's lit room
        starts at the map's edge), its size from the des MAP when the gym knows it — a room
        behind a closed door is not on the first screen (M2), so the screen cannot say. START: the
        robot's start cell in the MAP when the des pins it — the top-left is then where the robot
        stands less its start (a dark level: the first screen is the eight cells around it)."""
        ys, xs = np.where(chars != 32)
        self.y0, self.x0 = int(ys.min()), int(xs.min())
        at = np.argwhere(chars == ord("@"))
        if start is not None and len(at) == 1:
            self.y0, self.x0 = int(at[0][0]) - int(start[1]), int(at[0][1]) - int(start[0])
        self.h, self.w = int(ys.max() - ys.min() + 1), int(xs.max() - xs.min() + 1)
        if size:
            self.w, self.h = max(self.w, int(size[0])), max(self.h, int(size[1]))
        self.h, self.w = min(self.h, chars.shape[0] - self.y0), min(self.w, chars.shape[1] - self.x0)   # never past the screen
        self.seen_traps = {}

    def cells(self):
        return [cell(x, y) for y in range(self.h) for x in range(self.w)]

    def map_atoms(self, obs):
        g, c = obs["glyphs"], obs["chars"]
        sd = obs.get("screen_descriptions") if hasattr(obs, "get") else None
        atoms, names = set(), {"objects": set(), "monsters": set()}
        for y in range(self.h):
            for x in range(self.w):
                sy, sx = self.y0 + y, self.x0 + x
                gl, ch = int(g[sy, sx]), chr(c[sy, sx])
                C = cell(x, y)
                if ch == " ":
                    continue
                if ch == "@":
                    atoms.add("agent_at(%s)" % C); atoms.add("floor(%s)" % C)
                elif nethack.glyph_is_monster(gl):
                    name = nethack.permonst(nethack.glyph_to_mon(gl)).mname.replace(" ", "_")
                    atoms.add("monster(%s,%s)" % (name, C)); atoms.add("floor(%s)" % C); names["monsters"].add(name)
                    if sd is not None and bytes(sd[sy, sx]).decode(errors="ignore").strip("\x00").startswith("peaceful "):
                        atoms.add("peaceful(%s,%s)" % (name, C))
                elif nethack.glyph_is_object(gl):
                    name = (nethack.OBJ_NAME(nethack.objclass(nethack.glyph_to_obj(gl))) or "thing").replace(" ", "_")
                    atoms.add("obj(%s,%s)" % (name, C)); atoms.add("floor(%s)" % C); names["objects"].add(name)
                elif nethack.glyph_is_trap(gl):
                    kind = ch.replace("^", "trap")
                    self.seen_traps[C] = kind
                    atoms.add("trap(%s,%s)" % (kind, C)); atoms.add("floor(%s)" % C)
                elif ch in ".":
                    atoms.add("floor(%s)" % C)
                elif nethack.glyph_is_cmap(gl) and gl - nethack.GLYPH_CMAP_OFF in DOORS_OPEN:
                    atoms.add("door(%s,open)" % C)       # an open door draws as - or |, like a wall
                elif nethack.glyph_is_cmap(gl) and gl - nethack.GLYPH_CMAP_OFF in DOORS_CLOSED:
                    atoms.add("door(%s,closed)" % C)
                elif nethack.glyph_is_cmap(gl) and gl - nethack.GLYPH_CMAP_OFF == S_NDOOR:
                    atoms.add("floor(%s)" % C)           # a doorway (broken or empty)
                elif ch in "-|":
                    atoms.add("wall(%s)" % C)
                elif ch == "+":
                    atoms.add("door(%s,closed)" % C)
                elif ch == "#":
                    atoms.add("corridor(%s)" % C)
                elif ch == ">":
                    atoms.add("stairs_down(%s)" % C); atoms.add("floor(%s)" % C)
                elif ch == "<":
                    atoms.add("stairs_up(%s)" % C); atoms.add("floor(%s)" % C)
                else:
                    atoms.add("unknown(%s)" % C)
        for C, kind in self.seen_traps.items():
            atoms.add("trap(%s,%s)" % (kind, C))
        return atoms, names

    def status_atoms(self, obs):
        b = obs["blstats"]
        return {"hp(%d)" % int(b[nethack.NLE_BL_HP]), "hpmax(%d)" % int(b[nethack.NLE_BL_HPMAX]),
                "hunger(%s)" % HUNGER.get(int(b[nethack.NLE_BL_HUNGER]), "normal"), "turn(%d)" % int(b[nethack.NLE_BL_TIME])}

    def inventory_atoms(self, obs):
        out = set()
        for s in obs.get("inv_strs", []):
            t = bytes(s).decode(errors="ignore").strip("\x00").strip()
            if not t:
                continue
            m = re.match(r"(an?|the|\d+)\s+(?:\+\d\s+|-\d\s+|uncursed\s+|blessed\s+|cursed\s+)*(.+?)(\s*\(.*\))?$", t)
            name = (m.group(2) if m else t).strip()
            if m and m.group(1).isdigit() and int(m.group(1)) > 1 and name.endswith("s") and not name.endswith("ss"):
                name = name[:-1]                           # "2 apples" -> apple, "20 flint stones" -> flint_stone
            out.add("holds(%s)" % name.replace(" ", "_"))
        return out

    @staticmethod
    def message(obs):
        t = bytes(obs["message"]).decode(errors="ignore").strip("\x00").strip()
        kinds = []
        low = t.lower()
        for pat, kind in MESSAGES:
            if re.search(pat, low):
                kinds.append(kind)
        return t, (kinds or (["other"] if t else []))

    def perceive(self, obs):
        atoms, names = self.map_atoms(obs)
        atoms |= self.status_atoms(obs) | self.inventory_atoms(obs)
        text, kinds = self.message(obs)
        return {"atoms": sorted(atoms), "events": ["said(%s)" % k for k in kinds], "message": text, "names": {k: sorted(v) for k, v in names.items()}}

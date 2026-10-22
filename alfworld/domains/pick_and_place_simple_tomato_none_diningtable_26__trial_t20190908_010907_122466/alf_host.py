# The shim a generated package carries as its own alf_host.py: the world's host, found by
# walking up to world/alf_host.py, made with this package's directory (its game.json).
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = "/home/axadmin/repo/perotheia-packages/metis-worlds/alfworld/world"                      # the generator writes the world's absolute path here
_cands = [os.environ.get("METIS_ALF_WORLD") or "", WORLD]
_d = HERE
for _ in range(6):
    _d = os.path.dirname(_d)
    _cands.append(os.path.join(_d, "world"))
for _c in _cands:
    if _c and os.path.exists(os.path.join(_c, "alf_host.py")):
        sys.path.insert(0, _c)
        break
from alf_host import AlfHost  # noqa: E402

PAIRS = ()


def flips(atom):
    return None


def words(atom, names=None):
    return None


def make(case=None):
    return AlfHost(HERE, case)

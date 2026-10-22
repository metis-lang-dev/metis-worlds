# The shim a generated package carries as its own sw_host.py: the world's host, made with
# this package's directory (its task.json).
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = "/home/axadmin/repo/perotheia-packages/.wt/metis-worlds-sw/scienceworld/world"
for _c in [os.environ.get("METIS_SW_WORLD") or "", WORLD, os.path.join(os.path.dirname(os.path.dirname(HERE)), "world")]:
    if _c and os.path.exists(os.path.join(_c, "sw_host.py")):
        sys.path.insert(0, _c)
        break
from sw_host import SwHost  # noqa: E402

PAIRS = ()


def flips(atom):
    return None


def words(atom, names=None):
    return None


def make(case=None):
    return SwHost(HERE, case)

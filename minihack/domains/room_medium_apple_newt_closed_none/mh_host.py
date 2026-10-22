# The shim a generated package carries as its own mh_host.py: the world's host, made with
# this package's directory (its level.json).
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = "/home/axadmin/repo/perotheia-packages/metis-world-minihack/world"
for _c in [os.environ.get("METIS_MH_WORLD") or "", WORLD] + [os.path.join(os.path.dirname(HERE) if i == 0 else "", "world") for i in range(1)]:
    if _c and os.path.exists(os.path.join(_c, "mh_host.py")):
        sys.path.insert(0, _c)
        break
from mh_host import MhHost  # noqa: E402

PAIRS = ()


def flips(atom):
    return None


def words(atom, names=None):
    return None


def make(case=None):
    return MhHost(HERE, case)

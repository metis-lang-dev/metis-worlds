# The shim a generated package carries as its own mh_host.py: the world's host (world/mh_host.py:
# $METIS_MH_WORLD, else the generator's path below, else a world/ directory above the package,
# metis.host.world_host), made with this package's directory (its level.json).
import os

from metis.host import world_host

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = "__WORLD__"                      # the generator writes the world's absolute path here
MhHost = world_host(HERE, "mh_host", env="METIS_MH_WORLD", world=WORLD).MhHost

PAIRS = ()


def flips(atom):
    return None


def words(atom, names=None):
    return None


def make(case=None):
    return MhHost(HERE, case)

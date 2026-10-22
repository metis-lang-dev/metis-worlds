# The shim a generated package carries as its own alf_host.py: the world's host (world/alf_host.py:
# $METIS_ALF_WORLD, else the generator's path below, else a world/ directory above the package,
# metis.host.world_host), made with this package's directory (its game.json).
import os

from metis.host import world_host

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = "__WORLD__"                      # the generator writes the world's absolute path here
AlfHost = world_host(HERE, "alf_host", env="METIS_ALF_WORLD", world=WORLD).AlfHost

PAIRS = ()


def flips(atom):
    return None


def words(atom, names=None):
    return None


def make(case=None):
    return AlfHost(HERE, case)

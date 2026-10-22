# The shim a generated package carries as its own sw_host.py: the world's host (found through
# metis.host.world_host), made with this package's directory (its task.json).
import os

from metis.host import world_host

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = "__WORLD__"
SwHost = world_host(HERE, "sw_host", env="METIS_SW_WORLD", world=WORLD).SwHost

PAIRS = ()


def flips(atom):
    return None


def words(atom, names=None):
    return None


def make(case=None):
    return SwHost(HERE, case)

# The road member's host shim: the road world's host (metis-worlds road/world/road_host.py: $METIS_ROAD_WORLD, else a
# world/ directory above the package), made with this package's directory (its manifest: the clock, the shared).
import os

from metis.host import world_host

HERE = os.path.dirname(os.path.abspath(__file__))
RoadHost = world_host(HERE, "road_host", env="METIS_ROAD_WORLD").RoadHost

PAIRS = ()


def flips(atom):
    return None


def words(atom, names=None):
    return None


def make(case=None):
    return RoadHost(HERE, case)

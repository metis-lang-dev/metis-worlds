# The home package's host shim (the road's pattern): the home world's host (world/home_host.py: $METIS_HOME_WORLD,
# else a world/ directory above the package), so the manifest names a file inside the catalog root (domains/).
from metis.host import world_host

_world = world_host(__file__, "home_host", env="METIS_HOME_WORLD")

PAIRS, flips, words, key = _world.PAIRS, _world.flips, _world.words, _world.key
lights, air, media, scenes, comfort = _world.lights, _world.air, _world.media, _world.scenes, _world.comfort

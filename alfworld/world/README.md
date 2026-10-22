# alfworld/world — the world's code

The layout is in `../README.md`. This file keeps what every script here, and every new CLI over
it, must know about ALFWorld's own code.

## Two hazards in ALFWorld's game loader (found writing `semantic_map.py`, alf-demo 3a)

1. **It rewrites `sys.argv`.** Once a game has been opened through the host (`AlfHost` /
   `alf_gym.py`'s loader, through TextWorld's PDDL parsing), `sys.argv` reads
   `['…', 'domain', 'task']`. A CLI that reads its arguments *after* opening a game gets the
   wrong ones. `semantic_map.py`'s first run wrote its map to `./task`. **Read `sys.argv`
   first**, before any game is opened, as `semantic_map.py` and `map_export.py` do.
2. **The process can end hard at exit.** The game's child is torn down at interpreter
   shutdown, and the process can end before Python flushes files it still holds open. A
   `json.dump(x, open(path, "w"))` never reaches the disk, and nothing fails. **Write in a
   `with` block** (closed before the process ends), never through an unclosed file object.

Both apply to the THOR backend's half of `semantic_map.py` (step 1) and to any CLI that drives a
game and then writes (the experiments, the agentic loop's drivers in metis-loop/pi).

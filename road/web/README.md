# road/web — the road's own page

`../demo.sh` serves it under metis-agent's service. `world.html` and `world.js` are metis-worlds `web/`'s template, the worlds' common page, changed here alone. `road.js` stands where `map.js` does, `dash.js` is the dashboard under the view; `client.html` and `client-shim.js` hold the 3D view. `vendor/` holds the same copies of fsttm-web and the consoles' shell as the other worlds' pages, never edited here.

`client/` is sumo-web3d's built client (Sidewalk Labs), a copy kept here and changed for this page, under the Eclipse Public License 2.0, not the Apache License of metis-worlds: `client/NOTICE` says what changed. Licensing is per world. `client-shim.js` is ours: it answers the client's socket and fetches from the road's frames, so its backend and its SUMO are never started. sumo-dashboard's analyses are ideas here, no code of it.

The Traffic dock is sumo-gui's live controls over TraCI (scale, stop, remove, close a lane, lights), and adding cars, which sumo-gui does not offer (road_host.py `traffic`). The towns are `../maps`, CARLA's, converted by `../maps/build.sh`; its 3 big towns are not tracked.

## Marking a problem

The top bar's **mark event N** button: press it when you see a problem, and again (**end event N**, red) when it is over. Events count 1..N over the demo, across runs; a reload keeps the count, a new demo starts it again. Starting a new run ends an open event.

Each edge goes in the journal as a world line, `mark:N:start:TICK` or `mark:N:stop:TICK` (the JOURNAL dock's save has them), and in the run's `log.jsonl` as a row with the car's place: `{"mark": N, "edge": "start", "at_tick": ..., "scenario": ..., "seed": ..., "lane": ..., "s": ..., "v": ...}`.

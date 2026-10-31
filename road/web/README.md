# road/web — the road's own page

`../demo.sh` serves it under metis-agent's service. `world.html` and `world.js` are the page, `dash.js` the dashboard under the view; `client.html` and `client-shim.js` hold the 3D view. `vendor/` holds the same copies of fsttm-web and the consoles' shell as the other worlds' pages, never edited here.

`client/` is sumo-web3d's built client (Sidewalk Labs), a copy kept here and changed for this page, under the Eclipse Public License 2.0, not the Apache License of metis-worlds: `client/NOTICE` says what changed. Licensing is per world. `client-shim.js` is ours: it answers the client's socket and fetches from the road's frames, so its backend and its SUMO are never started. sumo-dashboard's analyses are ideas here, no code of it.

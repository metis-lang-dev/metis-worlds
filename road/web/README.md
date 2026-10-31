# road/web — the road's own page

`../demo.sh` serves it under metis-agent's service. `world.html` and `world.js` are the page; `client.html` and `client-shim.js` hold the 3D view.

The 3D client is sumo-web3d 1.0.1's built bundle (Sidewalk Labs, https://github.com/sidewalklabs/sumo-web3d), under the Eclipse Public License 2.0, not the
Apache License of metis-worlds. It is fetched, not shipped: `fetch_client.sh` downloads its PyPI sdist, checks the sha256 and unpacks it, unmodified, to the
gitignored `vendor/sumo-web3d/`. `client-shim.js` is our own: it answers the client's socket and fetches from
the road's frames, so its backend and its SUMO are never started; in the browser it also runs the bundle with its follow functions in reach (a text replace at load, the file on disk stays as fetched). sumo-dashboard's analyses are ideas here, no code of it.

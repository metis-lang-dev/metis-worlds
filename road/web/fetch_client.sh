#!/usr/bin/env bash
# road/web/fetch_client.sh — sumo-web3d's built client (Sidewalk Labs, EPL-2.0) from its PyPI sdist into vendor/sumo-web3d, unmodified and not tracked: the repo
# keeps this script, not the bundle (the architect's ruling, road-agent step 0; as nethack/build.sh fetches the game). Its own backend and SUMO are never started:
# client-shim.js, our own file beside it, answers its socket and fetches and finds its assets.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; OUT="$HERE/vendor/sumo-web3d"
URL=https://files.pythonhosted.org/packages/84/16/d2af40f50cce28c729c46b53ba5ad6c021127fcd88c46c12d44b32e82a3c/sumo-web3d-1.0.1.tar.gz
SHA=02718108e24c85f83a85cb9f44b740af75d328c070291886bc8abcb36899df84
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
curl -fsSL -o "$T/c.tgz" "$URL"
echo "$SHA  $T/c.tgz" | sha256sum -c - >/dev/null
rm -rf "$OUT"; mkdir -p "$OUT"
tar -xzf "$T/c.tgz" --strip-components=3 -C "$OUT" --wildcards '*/sumo_web3d/static/*'
echo "$OUT: $(du -sh "$OUT" | cut -f1)"

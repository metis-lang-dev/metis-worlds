#!/usr/bin/env bash
# minihack/nethack/build.sh — the real game for the web page: NetHack 3.6.6 from its source with the tile hints on
# (TTY_TILES_ESCCODES, off in every distribution's build, apt's too), installed under minihack/.nethack.
#   ./build.sh            download, verify, build, install    ./build.sh --check    say what is installed
# The tty then names each map cell's tile (ESC [ 1 ; 0 ; tile ; flags z); world/nh_tty.py reads them. Nothing is patched
# in the game's rules: the same version as nle 1.3.0's and apt's.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "$HERE")/.nethack"; SRC="$ROOT/src"
URL=https://www.nethack.org/download/3.6.6/nethack-366-src.tgz
SHA=cfde0c3ab6dd7c22ae82e1e5a59ab80152304eb23fb06e3129439271e5643ed2
GAME="$ROOT/install/games/nethack"
if [ "${1:-}" = --check ]; then "$GAME" --version | head -1; strings "$ROOT/install/games/lib/nethackdir/nethack" | grep -c '^vt_tiledata$' || true; exit; fi
mkdir -p "$ROOT"; cd "$ROOT"
[ -f src.tgz ] || curl -fsSL -o src.tgz "$URL"
echo "$SHA  src.tgz" | sha256sum -c -
rm -rf "$SRC"; mkdir "$SRC"; tar -xzf src.tgz -C "$SRC" --strip-components=1; cd "$SRC"
sed -i 's|^/\* #define TTY_TILES_ESCCODES \*/|#define TTY_TILES_ESCCODES|' include/config.h
# glibc >= 2.34's cdefs.h tests __has_attribute(__warn_unused_result__): the game's empty macro of that name breaks it
sed -i -e '/^#define __warn_unused_result__ /d' -e '/^#define warn_unused_result /d' include/tradstdc.h
# NETHACK_SEED in the environment seeds the game's random numbers (else as ever): a start or a restore + the same keys = the same
# game, for the loop's replay (world/nh_gym.py save, load). No level reseed then: one stream per process. No rule of the game changes
sed -i '/^sys_random_seed()/,/^}/ s|^    return seed;|    if (nh_getenv("NETHACK_SEED")) {\n        has_strong_rngseed = FALSE;\n        seed = (unsigned long) atoi(nh_getenv("NETHACK_SEED"));\n    }\n    return seed;|' sys/unix/unixmain.c
H=sys/unix/hints/linux
sed -i -e "s|^PREFIX=.*|PREFIX=$ROOT/install|" -e 's|^#WINSRC += tile.c|WINSRC += tile.c|' -e 's|^#WINOBJ += tile.o|WINOBJ += tile.o|' "$H"
sed -i -e 's|^CFLAGS+=-DCURSES_GRAPHICS|#&|' -e 's|^WINSRC = .*|WINSRC = $(WINTTYSRC)|' -e 's|^WINOBJ = .*|WINOBJ = $(WINTTYOBJ)|' -e 's|^WINLIB = .*|WINLIB = $(WINTTYLIB)|' "$H"
sed -i 's|^CFLAGS=-g -O |CFLAGS=-g -O -Wno-unused-result |' "$H"
(cd sys/unix && sh setup.sh hints/linux)
make all                                  # serial: the top Makefile's util and src race under -j
make install
"$GAME" --version | head -1

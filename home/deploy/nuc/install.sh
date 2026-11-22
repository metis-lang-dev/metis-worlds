#!/usr/bin/env bash
# Build metis-home natively (no container) and install its systemd user unit; it does NOT start or stop
# anything. The swap from the Python sidecar (fsttm-metis) is the operator's, printed at the end.
#
#   bash deploy/nuc/install.sh            # from the home world (metis-worlds home/)
#
# METIS_AGENT  the metis-agent checkout with cmd/metis-home (default ~/metis/metis-agent-home, branch main)
# METIS_LANG   metis-lang (default ~/metis/metis-lang): its runtime (libmetis_rt) is built with CMake if missing
# Needs: go >= 1.24, cmake, g++ (apt install golang-go cmake build-essential).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
AGENT="${METIS_AGENT:-$HOME/metis/metis-agent-home}"
LANG_DIR="${METIS_LANG:-$HOME/metis/metis-lang}"
[ -f "$AGENT/go/cmd/metis-home/main.go" ] || { echo "no cmd/metis-home in $AGENT (git -C ~/metis/metis-agent worktree add ../metis-agent-home origin/main)" >&2; exit 2; }
command -v go >/dev/null || { echo "no go: sudo apt install golang-go" >&2; exit 2; }
# the runtime library, natively
cmake -S "$LANG_DIR/runtime" -B "$LANG_DIR/runtime/build" -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build "$LANG_DIR/runtime/build" --target metis_rt -j"$(nproc)" >/dev/null
# metis-home links libmetis_rt only (rpath embedded); build.sh's cgo flags also name llama.cpp's headers, which the
# home does not use: point them at the runtime's when no llama.cpp checkout is around
cd "$AGENT/go"
export METIS_LANG_DIR="$LANG_DIR" CGO_CFLAGS="-I$LANG_DIR/runtime/c" \
       CGO_LDFLAGS="-Wl,--disable-new-dtags -L$LANG_DIR/runtime/build -Wl,-rpath,$LANG_DIR/runtime/build"
go build -o bin/metis-home ./cmd/metis-home
install -D -m 755 bin/metis-home "$HOME/.local/bin/metis-home"
install -D -m 644 "$HERE/metis-home.service" "$HOME/.config/systemd/user/metis-home.service"
systemctl --user daemon-reload
echo "installed: ~/.local/bin/metis-home, ~/.config/systemd/user/metis-home.service (not started)"
echo "swap in:   systemctl --user disable --now fsttm-metis && systemctl --user enable --now metis-home"
echo "roll back: systemctl --user disable --now metis-home && systemctl --user enable --now fsttm-metis"

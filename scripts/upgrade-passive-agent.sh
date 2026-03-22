#!/usr/bin/env bash
set -euo pipefail

PREFIX="${1:-/opt/grapheon}"
STATE_DIR="${2:-/var/lib/grapheon-agent}"
ENV_DEST="${3:-/etc/grapheon-agent.env}"
SYSTEMD_DIR="${4:-/etc/systemd/system}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SYSTEMCTL_BIN="${SYSTEMCTL_BIN:-systemctl}"
CURRENT_LINK="$PREFIX/agent/current"
TARGET_VERSION="$(cat "$REPO_ROOT/agent/VERSION")"
PREVIOUS_VERSION=""

if [[ -L "$CURRENT_LINK" && -f "$CURRENT_LINK/VERSION" ]]; then
  PREVIOUS_VERSION="$(cat "$CURRENT_LINK/VERSION")"
fi

bash "$SCRIPT_DIR/install-passive-agent.sh" "$PREFIX" "$STATE_DIR" "$ENV_DEST" "$SYSTEMD_DIR"

cat <<EOF
Passive agent upgrade complete.
Previous version: ${PREVIOUS_VERSION:-none}
Current version: $TARGET_VERSION

Rollback:
  bash scripts/rollback-passive-agent.sh ${PREVIOUS_VERSION:-<previous-version>}
EOF

if command -v "$SYSTEMCTL_BIN" >/dev/null 2>&1; then
  "$SYSTEMCTL_BIN" try-restart grapheon-agent.timer || true
fi

#!/usr/bin/env bash
set -euo pipefail

PURGE_STATE="false"
if [[ "${1:-}" == "--purge-state" ]]; then
  PURGE_STATE="true"
  shift
fi

PREFIX="${1:-/opt/grapheon}"
STATE_DIR="${2:-/var/lib/grapheon-agent}"
ENV_DEST="${3:-/etc/grapheon-agent.env}"
SYSTEMD_DIR="${4:-/etc/systemd/system}"
SYSTEMCTL_BIN="${SYSTEMCTL_BIN:-systemctl}"

if command -v "$SYSTEMCTL_BIN" >/dev/null 2>&1; then
  "$SYSTEMCTL_BIN" disable --now grapheon-agent.timer grapheon-agent.service >/dev/null 2>&1 || true
  "$SYSTEMCTL_BIN" daemon-reload || true
fi

rm -f "$SYSTEMD_DIR/grapheon-agent.service" "$SYSTEMD_DIR/grapheon-agent.timer"
rm -rf "$PREFIX/agent"
rm -f "$ENV_DEST"

if [[ "$PURGE_STATE" == "true" ]]; then
  rm -rf "$STATE_DIR"
fi

cat <<EOF
Passive agent removed.
State directory preserved: $([[ "$PURGE_STATE" == "true" ]] && echo "no" || echo "yes")
EOF

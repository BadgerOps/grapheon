#!/usr/bin/env bash
set -euo pipefail

TARGET_VERSION="${1:?Usage: rollback-passive-agent.sh <version> [prefix] [systemd_dir]}"
PREFIX="${2:-/opt/grapheon}"
SYSTEMD_DIR="${3:-/etc/systemd/system}"
SYSTEMCTL_BIN="${SYSTEMCTL_BIN:-systemctl}"

AGENT_ROOT="$PREFIX/agent"
RELEASE_DIR="$AGENT_ROOT/releases/$TARGET_VERSION"
CURRENT_LINK="$AGENT_ROOT/current"

if [[ ! -d "$RELEASE_DIR" ]]; then
  echo "Release version $TARGET_VERSION is not installed under $AGENT_ROOT/releases" >&2
  exit 1
fi

ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"

if command -v "$SYSTEMCTL_BIN" >/dev/null 2>&1; then
  "$SYSTEMCTL_BIN" daemon-reload
fi

cat <<EOF
Passive agent rollback complete.
Current runtime link: $CURRENT_LINK -> $RELEASE_DIR

To run the restored version immediately:
  systemctl start grapheon-agent.service
EOF

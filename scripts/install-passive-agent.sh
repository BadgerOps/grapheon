#!/usr/bin/env bash
set -euo pipefail

PREFIX="${1:-/opt/grapheon}"
STATE_DIR="${2:-/var/lib/grapheon-agent}"
ENV_DEST="${3:-/etc/grapheon-agent.env}"
SYSTEMD_DIR="${4:-/etc/systemd/system}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

install -d -m 0755 "$PREFIX/agent"
install -d -m 0700 "$STATE_DIR"

install -m 0644 "$REPO_ROOT/agent/__init__.py" "$PREFIX/agent/__init__.py"
install -m 0644 "$REPO_ROOT/agent/VERSION" "$PREFIX/agent/VERSION"
install -m 0755 "$REPO_ROOT/agent/grapheon_agent.py" "$PREFIX/agent/grapheon_agent.py"
install -m 0644 "$REPO_ROOT/deploy/grapheon-agent.service" "$SYSTEMD_DIR/grapheon-agent.service"
install -m 0644 "$REPO_ROOT/deploy/grapheon-agent.timer" "$SYSTEMD_DIR/grapheon-agent.timer"

if [[ ! -f "$ENV_DEST" ]]; then
  install -m 0600 "$REPO_ROOT/deploy/grapheon-agent.env.example" "$ENV_DEST"
  echo "Wrote example environment file to $ENV_DEST"
else
  echo "Environment file already exists at $ENV_DEST; leaving it unchanged"
fi

systemctl daemon-reload

cat <<EOF
Passive agent files installed.

Next steps:
1. Edit $ENV_DEST and set GRAPHEON_AGENT_SERVER_URL plus GRAPHEON_AGENT_ENROLLMENT_KEY
2. Run: systemctl start grapheon-agent.service
3. Approve the pending agent in Graphēon if required
4. Run: systemctl start grapheon-agent.service
5. Enable periodic runs: systemctl enable --now grapheon-agent.timer
EOF

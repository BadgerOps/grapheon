#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION="${1:-$(cat "$REPO_ROOT/agent/VERSION")}"
OUTPUT_PATH="${2:-$REPO_ROOT/dist/grapheon-agent-v$VERSION.tar.gz}"

STAGE_DIR="$(mktemp -d)"
ARCHIVE_ROOT="$STAGE_DIR/grapheon-agent-v$VERSION"

cleanup() {
  rm -rf "$STAGE_DIR"
}
trap cleanup EXIT

mkdir -p "$ARCHIVE_ROOT/agent" "$ARCHIVE_ROOT/deploy" "$ARCHIVE_ROOT/docs" "$ARCHIVE_ROOT/scripts"

install -m 0644 "$REPO_ROOT/agent/README.md" "$ARCHIVE_ROOT/agent/README.md"
install -m 0644 "$REPO_ROOT/agent/VERSION" "$ARCHIVE_ROOT/agent/VERSION"
install -m 0644 "$REPO_ROOT/agent/CHANGELOG.md" "$ARCHIVE_ROOT/agent/CHANGELOG.md"
install -m 0644 "$REPO_ROOT/agent/Dockerfile" "$ARCHIVE_ROOT/agent/Dockerfile"
install -m 0644 "$REPO_ROOT/agent/__init__.py" "$ARCHIVE_ROOT/agent/__init__.py"
install -m 0755 "$REPO_ROOT/agent/grapheon_agent.py" "$ARCHIVE_ROOT/agent/grapheon_agent.py"
install -m 0644 "$REPO_ROOT/deploy/grapheon-agent.env.example" "$ARCHIVE_ROOT/deploy/grapheon-agent.env.example"
install -m 0644 "$REPO_ROOT/deploy/grapheon-agent.service" "$ARCHIVE_ROOT/deploy/grapheon-agent.service"
install -m 0644 "$REPO_ROOT/deploy/grapheon-agent.timer" "$ARCHIVE_ROOT/deploy/grapheon-agent.timer"
install -m 0755 "$REPO_ROOT/scripts/install-passive-agent.sh" "$ARCHIVE_ROOT/scripts/install-passive-agent.sh"
install -m 0755 "$REPO_ROOT/scripts/upgrade-passive-agent.sh" "$ARCHIVE_ROOT/scripts/upgrade-passive-agent.sh"
install -m 0755 "$REPO_ROOT/scripts/rollback-passive-agent.sh" "$ARCHIVE_ROOT/scripts/rollback-passive-agent.sh"
install -m 0755 "$REPO_ROOT/scripts/uninstall-passive-agent.sh" "$ARCHIVE_ROOT/scripts/uninstall-passive-agent.sh"
install -m 0644 "$REPO_ROOT/docs/agent_quickstart.md" "$ARCHIVE_ROOT/docs/agent_quickstart.md"

mkdir -p "$(dirname "$OUTPUT_PATH")"
tar -C "$STAGE_DIR" -czf "$OUTPUT_PATH" "grapheon-agent-v$VERSION"
echo "$OUTPUT_PATH"

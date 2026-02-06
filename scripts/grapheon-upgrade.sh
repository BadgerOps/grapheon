#!/usr/bin/env bash
# grapheon-upgrade.sh — Host-level upgrade watcher script
#
# Triggered by systemd path unit when /data/upgrade-requested appears.
# Reads the requested version, pulls new container images, restarts services,
# runs a health check, and writes status to /data/upgrade-status.json.
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
REQUEST_FILE="${DATA_DIR}/upgrade-requested"
STATUS_FILE="${DATA_DIR}/upgrade-status.json"
HEALTH_URL="http://localhost:8000/api/health"
HEALTH_TIMEOUT=30
PULL_TIMEOUT=300

BACKEND_IMAGE="ghcr.io/badgerops/grapheon-backend"
FRONTEND_IMAGE="ghcr.io/badgerops/grapheon-frontend"

log() { echo "[$(date -Iseconds)] $*"; }

write_status() {
  local status="$1"
  shift
  local msg="${*:-}"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  cat > "${STATUS_FILE}" <<EOF
{
  "status": "${status}",
  "message": "${msg}",
  "updated_at": "${ts}"
}
EOF
  log "Status → ${status}: ${msg}"
}

cleanup() {
  rm -f "${REQUEST_FILE}"
  log "Cleaned up ${REQUEST_FILE}"
}

# ── Guard: request file must exist ─────────────────────────────────
if [[ ! -f "${REQUEST_FILE}" ]]; then
  log "No upgrade request file found at ${REQUEST_FILE}. Exiting."
  exit 0
fi

# ── Read target version from request ───────────────────────────────
TARGET_VERSION="$(python3 -c "
import json, sys
try:
    data = json.load(open('${REQUEST_FILE}'))
    print(data.get('target_version', ''))
except Exception as e:
    print('', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null || echo "")"

if [[ -z "${TARGET_VERSION}" ]]; then
  write_status "failed" "Could not read target version from ${REQUEST_FILE}"
  cleanup
  exit 1
fi

log "Upgrade requested → v${TARGET_VERSION}"

# ── Mark upgrade as running ────────────────────────────────────────
write_status "running" "Pulling images for v${TARGET_VERSION}..."

# ── Pull new images ────────────────────────────────────────────────
log "Pulling ${BACKEND_IMAGE}:v${TARGET_VERSION}"
if ! timeout "${PULL_TIMEOUT}" podman pull "${BACKEND_IMAGE}:v${TARGET_VERSION}"; then
  write_status "failed" "Failed to pull backend image v${TARGET_VERSION}"
  cleanup
  exit 1
fi

log "Pulling ${FRONTEND_IMAGE}:v${TARGET_VERSION}"
if ! timeout "${PULL_TIMEOUT}" podman pull "${FRONTEND_IMAGE}:v${TARGET_VERSION}"; then
  write_status "failed" "Failed to pull frontend image v${TARGET_VERSION}"
  cleanup
  exit 1
fi

write_status "running" "Images pulled. Restarting services..."

# ── Restart systemd services ───────────────────────────────────────
log "Restarting grapheon-backend and grapheon-frontend services"
if ! systemctl restart grapheon-backend.service grapheon-frontend.service; then
  write_status "failed" "Failed to restart systemd services"
  cleanup
  exit 1
fi

write_status "running" "Services restarted. Running health check..."

# ── Health check ───────────────────────────────────────────────────
log "Waiting for health check at ${HEALTH_URL} (timeout: ${HEALTH_TIMEOUT}s)"
HEALTH_OK=false
for i in $(seq 1 "${HEALTH_TIMEOUT}"); do
  if curl -sf "${HEALTH_URL}" > /dev/null 2>&1; then
    HEALTH_OK=true
    log "Health check passed after ${i}s"
    break
  fi
  sleep 1
done

if [[ "${HEALTH_OK}" != "true" ]]; then
  write_status "failed" "Health check failed after ${HEALTH_TIMEOUT}s"
  cleanup
  exit 1
fi

# ── Success ────────────────────────────────────────────────────────
write_status "completed" "Upgrade to v${TARGET_VERSION} completed successfully"
cleanup
log "Upgrade to v${TARGET_VERSION} finished successfully"

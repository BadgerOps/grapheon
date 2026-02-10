#!/usr/bin/env bash
# grapheon-upgrade.sh — Host-level upgrade watcher script
#
# Triggered by systemd path unit when /data/upgrade-requested appears.
# Reads the requested version, backs up data, pulls new container images,
# restarts services, runs a health check, and writes status to
# /data/upgrade-status.json with step-by-step progress tracking.
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
REQUEST_FILE="${DATA_DIR}/upgrade-requested"
STATUS_FILE="${DATA_DIR}/upgrade-status.json"
BACKUP_DIR="${DATA_DIR}/backups"
HEALTH_URL="http://localhost:8000/api/health"
HEALTH_TIMEOUT=30
PULL_TIMEOUT=300

BACKEND_IMAGE="ghcr.io/badgerops/grapheon-backend"
FRONTEND_IMAGE="ghcr.io/badgerops/grapheon-frontend"

TOTAL_STEPS=5

log() { echo "[$(date -Iseconds)] $*"; }

write_status() {
  local status="$1"
  local step="$2"
  local msg="$3"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  # Calculate progress percentage from step number
  local progress=0
  if [[ "${step}" -gt 0 ]]; then
    progress=$(( (step * 100) / TOTAL_STEPS ))
  fi
  # Clamp completed to 100
  if [[ "${status}" == "completed" ]]; then
    progress=100
  fi
  cat > "${STATUS_FILE}" <<EOF
{
  "status": "${status}",
  "message": "${msg}",
  "step": ${step},
  "total_steps": ${TOTAL_STEPS},
  "progress": ${progress},
  "updated_at": "${ts}"
}
EOF
  log "Status → ${status} (step ${step}/${TOTAL_STEPS}, ${progress}%): ${msg}"
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

# ── Read target versions from request ──────────────────────────────
read -r BACKEND_VERSION FRONTEND_VERSION < <(python3 -c "
import json, sys
try:
    data = json.load(open('${REQUEST_FILE}'))
    bv = data.get('target_backend_version', data.get('target_version', ''))
    fv = data.get('target_frontend_version', bv)
    print(bv, fv)
except Exception as e:
    print('', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null || echo "")

if [[ -z "${BACKEND_VERSION}" ]]; then
  write_status "failed" 0 "Could not read target version from ${REQUEST_FILE}"
  cleanup
  exit 1
fi

# Fall back to backend version if frontend version is missing
if [[ -z "${FRONTEND_VERSION}" ]]; then
  FRONTEND_VERSION="${BACKEND_VERSION}"
fi

log "Upgrade requested → backend v${BACKEND_VERSION}, frontend v${FRONTEND_VERSION}"

# ── Step 1: Backup data ───────────────────────────────────────────
BACKUP_TIMESTAMP="$(date +%Y-%m-%d-%H%M%S)"
BACKUP_FILENAME="grapheon-backup-${BACKUP_TIMESTAMP}.tar.gz"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILENAME}"

write_status "running" 1 "Backing up data to ${BACKUP_FILENAME}..."

mkdir -p "${BACKUP_DIR}"

# Build list of items to back up (only those that exist)
BACKUP_ITEMS=()
for item in "${DATA_DIR}/grapheon.db" "${DATA_DIR}/grapheon.db-wal" "${DATA_DIR}/grapheon.db-shm" "${DATA_DIR}/config.json" "${DATA_DIR}/.env"; do
  if [[ -e "${item}" ]]; then
    BACKUP_ITEMS+=("${item}")
  fi
done

if [[ ${#BACKUP_ITEMS[@]} -gt 0 ]]; then
  if ! tar -czf "${BACKUP_PATH}" "${BACKUP_ITEMS[@]}" 2>/dev/null; then
    write_status "failed" 1 "Failed to create backup at ${BACKUP_PATH}"
    cleanup
    exit 1
  fi
  log "Backup created: ${BACKUP_PATH}"
else
  log "No data files found to back up, continuing"
fi

# ── Step 2: Pull backend image ────────────────────────────────────
write_status "running" 2 "Pulling backend image v${BACKEND_VERSION}..."

log "Pulling ${BACKEND_IMAGE}:v${BACKEND_VERSION}"
if ! timeout "${PULL_TIMEOUT}" podman pull "${BACKEND_IMAGE}:v${BACKEND_VERSION}"; then
  write_status "failed" 2 "Failed to pull backend image v${BACKEND_VERSION}"
  cleanup
  exit 1
fi

# ── Step 3: Pull frontend image ───────────────────────────────────
write_status "running" 3 "Pulling frontend image v${FRONTEND_VERSION}..."

log "Pulling ${FRONTEND_IMAGE}:v${FRONTEND_VERSION}"
if ! timeout "${PULL_TIMEOUT}" podman pull "${FRONTEND_IMAGE}:v${FRONTEND_VERSION}"; then
  write_status "failed" 3 "Failed to pull frontend image v${FRONTEND_VERSION}"
  cleanup
  exit 1
fi

# ── Step 4: Restart services ──────────────────────────────────────
write_status "running" 4 "Restarting services..."

log "Restarting grapheon-backend and grapheon-frontend services"
if ! systemctl restart grapheon-backend.service grapheon-frontend.service; then
  write_status "failed" 4 "Failed to restart systemd services"
  cleanup
  exit 1
fi

# ── Step 5: Health check ──────────────────────────────────────────
write_status "running" 5 "Running health check..."

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
  write_status "failed" 5 "Health check failed after ${HEALTH_TIMEOUT}s"
  cleanup
  exit 1
fi

# ── Success ────────────────────────────────────────────────────────
write_status "completed" ${TOTAL_STEPS} "Upgrade completed (backend v${BACKEND_VERSION}, frontend v${FRONTEND_VERSION})"
cleanup
log "Upgrade finished (backend v${BACKEND_VERSION}, frontend v${FRONTEND_VERSION})"

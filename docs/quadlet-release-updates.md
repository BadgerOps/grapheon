# Release Update Pipeline (Systemd + Podman)

This document describes the current container deployment/update model used by Graphēon: systemd-managed Podman services, not Quadlet units.

## Current Deployment Model

- CI publishes backend/frontend images to GHCR from `master` when a new component version tag is needed.
- The host runs long-lived systemd services for backend and frontend containers:
  - `grapheon-backend.service`
  - `grapheon-frontend.service`
- Optional edge ingress uses `cloudflared.service`.
- Backend data is persisted on the host (SQLite volume), not inside ephemeral containers.

## Release Artifacts

Release tags/images are component-scoped:

- Tags: `backend-vX.Y.Z`, `frontend-vX.Y.Z`
- Images:
  - `ghcr.io/badgerops/grapheon-backend:latest`
  - `ghcr.io/badgerops/grapheon-backend:vX.Y.Z`
  - `ghcr.io/badgerops/grapheon-frontend:latest`
  - `ghcr.io/badgerops/grapheon-frontend:vX.Y.Z`

See `docs/release-process.md` for versioning and tagging behavior.

## Service Expectations

The upgrade script expects systemd service names:

- `grapheon-backend.service`
- `grapheon-frontend.service`

And backend runtime defaults:

- `DATABASE_URL=sqlite:///./data/network.db`
- Persistent data mounted to `/app/data`

## Manual Update Workflow

Use this when you want an explicit operator-driven update:

```bash
podman pull ghcr.io/badgerops/grapheon-backend:vX.Y.Z
podman pull ghcr.io/badgerops/grapheon-frontend:vX.Y.Z
sudo systemctl restart grapheon-backend.service grapheon-frontend.service
```

Verify:

```bash
curl -sf http://localhost:8000/health
sudo systemctl status grapheon-backend.service grapheon-frontend.service
```

## In-App Upgrade Workflow

Graphēon supports an in-app upgrade trigger from Settings.

Flow:

1. Frontend calls `POST /api/updates/upgrade`.
2. Backend writes `/data/upgrade-requested`.
3. `grapheon-upgrade.path` detects the marker file.
4. `grapheon-upgrade.service` runs `scripts/grapheon-upgrade.sh`.
5. Script pulls target backend/frontend tags, restarts systemd services, then health-checks backend.
6. Script writes progress/result to `/data/upgrade-status.json`.
7. Frontend polls `GET /api/updates/status`.

## Host Setup for In-App Upgrades

Install the shipped units/script:

```bash
sudo mkdir -p /opt/grapheon/scripts
sudo cp scripts/grapheon-upgrade.sh /opt/grapheon/scripts/
sudo chmod +x /opt/grapheon/scripts/grapheon-upgrade.sh

sudo cp deploy/grapheon-upgrade.path /etc/systemd/system/
sudo cp deploy/grapheon-upgrade.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now grapheon-upgrade.path
```

## Rollback

Rollback is service-image driven:

1. Update your service definition to point to the previous image tag.
2. Restart services:

```bash
sudo systemctl daemon-reload
sudo systemctl restart grapheon-backend.service grapheon-frontend.service
```

3. Clear stale upgrade markers if needed:

```bash
rm -f /data/upgrade-requested /data/upgrade-status.json
```

## Notes

- Make sure the host is authenticated to GHCR if images are private: `podman login ghcr.io`.
- Keep `/app/data` mapped to persistent host storage.
- This doc intentionally replaces prior Quadlet-specific instructions.

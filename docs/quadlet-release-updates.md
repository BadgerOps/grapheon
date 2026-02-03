# Quadlet Release Update Pipeline (NixOS + Podman + Cloudflare Tunnel)

This document describes how to automatically update the backend and frontend containers on a NixOS server when a new GitHub Release is cut. It assumes you are running Graphēon in Podman via Quadlet units and exposing it via Cloudflare Tunnel.

## Overview

- **CI/CD** builds and publishes container images to GHCR on each release.
- **Quadlet** units reference `:latest` (or a specific version tag).
- **Podman auto-update** detects new image digests and restarts containers.

## Release Trigger (GitHub)

Use GitHub Releases tagged per component so frontend and backend can ship independently. The release workflow runs on pushes to `master`, creates tags/releases if they do not exist, and builds/pushes images. Tag format:

- `backend-vX.Y.Z`
- `frontend-vX.Y.Z`

- `ghcr.io/badgerops/grapheon-backend:latest`
- `ghcr.io/badgerops/grapheon-backend:vX.Y.Z`
- `ghcr.io/badgerops/grapheon-frontend:latest`
- `ghcr.io/badgerops/grapheon-frontend:vX.Y.Z`

Release workflow outline:

1. Trigger on `push` to `master`.
2. Create `backend-vX.Y.Z` and/or `frontend-vX.Y.Z` if they do not exist.
3. Build backend and/or frontend images.
4. Push both `latest` and version tag to GHCR.

## Container Definitions

- Backend image is built from `backend/Dockerfile`.
- Frontend image is built from `frontend/Dockerfile` and serves static assets via nginx.
- The frontend nginx config proxies `/api` to `http://grapheon-backend:8000`.

## Quadlet Configuration

Example Quadlet container unit (`/etc/containers/systemd/grapheon-backend.container`):

```
[Container]
Image=ghcr.io/badgerops/grapheon-backend:latest
AutoUpdate=registry
ContainerName=grapheon-backend
Network=grapheon
Volume=/var/lib/grapheon/data:/data:Z
Environment=DATABASE_URL=sqlite:///data/network.db
Environment=APP_NAME=Graphēon
Environment=APP_VERSION=0.1.0
Port=8000:8000
```

Frontend Quadlet (`/etc/containers/systemd/grapheon-frontend.container`):

```
[Container]
Image=ghcr.io/badgerops/grapheon-frontend:latest
AutoUpdate=registry
ContainerName=grapheon-frontend
Network=grapheon
Port=8080:8080
```

Cloudflared Quadlet (`/etc/containers/systemd/cloudflared.container`):

```
[Container]
Image=cloudflare/cloudflared:latest
AutoUpdate=registry
ContainerName=cloudflared
Network=grapheon
Exec= tunnel --config /etc/cloudflared/config.yml run
Volume=/etc/cloudflared:/etc/cloudflared:Z
```

## Podman Auto-Update

Enable Podman’s auto-update timer on NixOS so containers update after a new image is pushed:

```
# configuration.nix
services.podman = {
  enable = true;
  autoUpdate.enable = true;
  autoUpdate.dates = "daily"; # or hourly
};
```

This will run `podman auto-update`, which checks image digests for containers with `AutoUpdate=registry`.

## NixOS Systemd Setup (Quadlet)

Enable the Quadlet generator and reload systemd:

```
systemctl daemon-reload
systemctl enable --now grapheon-backend.service
systemctl enable --now grapheon-frontend.service
systemctl enable --now cloudflared.service
```

## Manual Update (On Demand)

```
podman auto-update
systemctl status grapheon-backend grapheon-frontend cloudflared
```

## Rollback

If a release is bad, point Quadlet units at a previous tag (e.g., `:v0.1.2`) and restart:

```
systemctl restart grapheon-backend grapheon-frontend
```

## Notes

- Make sure GHCR images are public or the server is logged in with `podman login ghcr.io`.
- Keep DB data in a persistent host volume (`/var/lib/grapheon/data`).
- Cloudflare Tunnel exposes only the frontend; the frontend should proxy `/api` to the backend.

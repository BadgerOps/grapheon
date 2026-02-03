# Quadlet Release Update Pipeline (NixOS + Podman + Cloudflare Tunnel)

This document describes how to automatically update the backend and frontend containers on a NixOS server when a new GitHub Release is cut. It assumes you are running Graphēon in Podman via Quadlet units and exposing it via Cloudflare Tunnel.

## Overview

- **CI/CD** builds and publishes container images to GHCR on each release.
- **Quadlet** units reference `:latest` (or a specific version tag).
- **Podman auto-update** detects new image digests and restarts containers.

## Release Trigger (GitHub)

Add a release workflow that builds and pushes images when a release is published. Example tags:

- `ghcr.io/badgerops/grapheon-backend:latest`
- `ghcr.io/badgerops/grapheon-backend:vX.Y.Z`
- `ghcr.io/badgerops/grapheon-frontend:latest`
- `ghcr.io/badgerops/grapheon-frontend:vX.Y.Z`

Release workflow outline:

1. Trigger on `release.published`.
2. Build backend and frontend images.
3. Push both `latest` and version tag to GHCR.

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

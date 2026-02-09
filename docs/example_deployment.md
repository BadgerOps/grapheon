# Alternative Deployment: NixOS + Podman + systemd

This document describes an alternative deployment model using NixOS with Podman containers managed by systemd services. For the standard Docker deployment, see `docs/deployment.md`.

This approach adds systemd-driven lifecycle management and in-app upgrade automation via `deploy/grapheon-upgrade.path`, `deploy/grapheon-upgrade.service`, and `scripts/grapheon-upgrade.sh`.

## Runtime Topology

- `grapheon-backend.service` runs `ghcr.io/badgerops/grapheon-backend` (port 8000).
- `grapheon-frontend.service` runs `ghcr.io/badgerops/grapheon-frontend` (port 8080).
- Backend data persists on host storage and is mounted to `/app/data` in the backend container.
- Backend health endpoint is `http://localhost:8000/health`.

## Image Tags

Release workflow publishes:

- `ghcr.io/badgerops/grapheon-backend:latest` and `:vX.Y.Z`
- `ghcr.io/badgerops/grapheon-frontend:latest` and `:vX.Y.Z`

## NixOS Host Configuration (Example)

The following example shows a systemd-driven Podman deployment in `configuration.nix`.

```nix
{ config, pkgs, ... }:
{
  virtualisation.podman.enable = true;

  systemd.services.grapheon-backend = {
    description = "Graphēon backend container";
    wantedBy = [ "multi-user.target" ];
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
    serviceConfig = {
      Restart = "always";
      ExecStartPre = [
        "${pkgs.podman}/bin/podman rm -f grapheon-backend || true"
      ];
      ExecStart = ''
        ${pkgs.podman}/bin/podman run --name grapheon-backend \
          -p 8000:8000 \
          -v /var/lib/grapheon/data:/app/data:Z \
          -e DATABASE_URL=sqlite:///./data/network.db \
          -e ENFORCE_AUTH=True \
          ghcr.io/badgerops/grapheon-backend:latest
      '';
      ExecStop = "${pkgs.podman}/bin/podman stop -t 15 grapheon-backend";
      ExecStopPost = "${pkgs.podman}/bin/podman rm -f grapheon-backend || true";
    };
  };

  systemd.services.grapheon-frontend = {
    description = "Graphēon frontend container";
    wantedBy = [ "multi-user.target" ];
    after = [ "network-online.target" "grapheon-backend.service" ];
    wants = [ "network-online.target" ];
    serviceConfig = {
      Restart = "always";
      ExecStartPre = [
        "${pkgs.podman}/bin/podman rm -f grapheon-frontend || true"
      ];
      ExecStart = ''
        ${pkgs.podman}/bin/podman run --name grapheon-frontend \
          -p 8080:8080 \
          ghcr.io/badgerops/grapheon-frontend:latest
      '';
      ExecStop = "${pkgs.podman}/bin/podman stop -t 15 grapheon-frontend";
      ExecStopPost = "${pkgs.podman}/bin/podman rm -f grapheon-frontend || true";
    };
  };
}
```

Apply config:

```bash
sudo nixos-rebuild switch
sudo systemctl status grapheon-backend.service grapheon-frontend.service
```

## Upgrade Flows

### Manual update

```bash
podman pull ghcr.io/badgerops/grapheon-backend:vX.Y.Z
podman pull ghcr.io/badgerops/grapheon-frontend:vX.Y.Z
sudo systemctl restart grapheon-backend.service grapheon-frontend.service
curl -sf http://localhost:8000/health
```

### In-app upgrade trigger

The app-driven upgrade flow uses files under `/data`:

1. `POST /api/updates/upgrade` writes `/data/upgrade-requested`.
2. `grapheon-upgrade.path` watches for that file.
3. `grapheon-upgrade.service` runs `/opt/grapheon/scripts/grapheon-upgrade.sh`.
4. The script pulls tagged images, restarts `grapheon-backend.service` + `grapheon-frontend.service`, and writes `/data/upgrade-status.json`.

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

1. Pin service image tags to a previous version.
2. Reload and restart services:

```bash
sudo systemctl daemon-reload
sudo systemctl restart grapheon-backend.service grapheon-frontend.service
```

3. Clear stale upgrade marker/status if needed:

```bash
rm -f /data/upgrade-requested /data/upgrade-status.json
```

## Operational Notes

- Ensure GHCR access on the host if images are private: `podman login ghcr.io`.
- Keep `/var/lib/grapheon/data` persistent and backed up.
- Service names should stay `grapheon-backend.service` and `grapheon-frontend.service`; upgrade automation depends on those names.
- For the standard Docker deployment (without systemd/Podman), see `docs/deployment.md`.

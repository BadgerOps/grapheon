# Graphēon

Graphēon ingests network scan outputs (nmap, netstat, arp, ping, traceroute, pcap), normalizes them, tags entities, and correlates related hosts. The stack is FastAPI + SQLite on the backend and Vite + React on the frontend. Python 3.12 is the standard runtime.

**Why Graphēon?** The name evokes graphing and mapping: this project fuses disparate network signals into a coherent graph of hosts, edges, and topology, which is exactly the product's core purpose.

Network topologies can be exported as **GraphML** (for Gephi, yEd, Cytoscape Desktop) or **draw.io** (for diagrams.net) directly from the map UI or the REST API.

## Quickstart

Use Nix for a consistent Python 3.12 and Node environment.

```bash
nix develop
```

Backend:

```bash
nix develop -c bash -lc "cd backend && uvicorn main:app --reload"
```

Frontend:

```bash
nix develop -c bash -lc "cd frontend && npm run dev"
```

## Tests

```bash
nix develop -c .venv/bin/python -m pytest
```

## Authentication

Graphēon supports multi-provider OIDC authentication (Okta, Google, GitHub, GitLab, Authentik) with 3-tier RBAC (admin/editor/viewer) and a local admin fallback.

**Quick start — local admin only:**

```bash
export LOCAL_ADMIN_USERNAME=admin
export LOCAL_ADMIN_EMAIL=admin@example.com
export LOCAL_ADMIN_PASSWORD=changeme
export JWT_SECRET=$(openssl rand -hex 32)
```

The admin user is created automatically on first startup. Auth is enabled by default but not enforced (`ENFORCE_AUTH=False`), so existing deployments continue to work without interruption.

Set `ENFORCE_AUTH=True` when ready to require login for all users.

See `docs/auth_provider.md` for the full setup guide including OIDC provider configuration, role mapping, and container deployment.

## Docs

See `docs/README.md` for the full documentation index, `docs/deployment.md` for the deployment guide, and `docs/auth_provider.md` for authentication setup.

## Deployment

Graphēon runs as two Docker containers: a **backend** (FastAPI on port 8000) and a **frontend** (nginx on port 8080). The frontend container proxies `/api` requests to the backend.

```bash
# Pull images
docker pull ghcr.io/badgerops/grapheon-backend:latest
docker pull ghcr.io/badgerops/grapheon-frontend:latest

# Run backend
docker run -d --name grapheon-backend \
  -p 8000:8000 \
  -v grapheon-data:/app/data \
  -e JWT_SECRET="$(openssl rand -hex 32)" \
  -e LOCAL_ADMIN_USERNAME=admin \
  -e LOCAL_ADMIN_EMAIL=admin@example.com \
  -e LOCAL_ADMIN_PASSWORD=changeme \
  ghcr.io/badgerops/grapheon-backend:latest

# Run frontend
docker run -d --name grapheon-frontend \
  -p 8080:8080 \
  --link grapheon-backend:grapheon-backend \
  ghcr.io/badgerops/grapheon-frontend:latest
```

Access the UI at `http://localhost:8080`. See `docs/deployment.md` for the full guide including docker compose examples.

## Container Releases

Graphēon publishes separate backend and frontend images to GHCR on pushes to `master` when a new version is detected:

- Backend tags use `backend-vX.Y.Z`
- Frontend tags use `frontend-vX.Y.Z`

The release workflow builds:

- `ghcr.io/badgerops/grapheon-backend:latest` and `:vX.Y.Z`
- `ghcr.io/badgerops/grapheon-frontend:latest` and `:vX.Y.Z`

See `docs/release-process.md` and `docs/example_deployment.md` for the full workflow.

## Data Hygiene

- Do not commit `.env` files or scan outputs like `*.xml`.
- Do not commit binary artifacts such as databases or pcaps.

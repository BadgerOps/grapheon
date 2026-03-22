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

The admin user is created automatically on first startup. Auth is enabled by default but not fully enforced (`ENFORCE_AUTH=False`): read-only endpoints remain accessible without login, but write/admin actions require authentication.

Set `ENFORCE_AUTH=True` when ready to require login for all users.

See `docs/auth_provider.md` for the full setup guide including OIDC provider configuration, role mapping, and container deployment.

## Docs

See `docs/README.md` for the full documentation index, `docs/deployment.md` for the deployment guide, `docs/auth_provider.md` for authentication setup, `docs/agents.md` for the passive agent backend and enrollment/API-key model, and `docs/agent_quickstart.md` for a step-by-step bootstrap and check-in walkthrough.

## Passive Agents

Graphēon now includes the first passive agent slice end to end: agent registry records, enrollment keys, approval workflow, low-impact policy profiles, an outbound-only check-in API, and a lightweight host-side runtime with `systemd` service/timer units. The current bootstrap model uses admin-created enrollment keys and one per-agent API key after approval.

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

## Component Releases

Graphēon publishes separate backend, frontend, and passive-agent releases on pushes to `master` when a new version is detected:

- Backend tags use `backend-vX.Y.Z`
- Frontend tags use `frontend-vX.Y.Z`
- Agent tags use `agent-vX.Y.Z`

The release workflow builds and publishes:

- `ghcr.io/badgerops/grapheon-backend:latest` and `:vX.Y.Z`
- `ghcr.io/badgerops/grapheon-frontend:latest` and `:vX.Y.Z`
- `ghcr.io/badgerops/grapheon-agent:latest` and `:vX.Y.Z`
- `grapheon-agent-vX.Y.Z.tar.gz` as a GitHub release artifact on the matching `agent-vX.Y.Z` release
- `grapheon-agent-vX.Y.Z.tar.gz.sha256` checksum file for artifact verification

See `docs/release-process.md` and `docs/example_deployment.md` for the full workflow.

## Data Hygiene

- Do not commit `.env` files or scan outputs like `*.xml`.
- Do not commit binary artifacts such as databases or pcaps.

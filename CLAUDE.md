# CLAUDE.md — Graphēon

## Project Overview

Graphēon ingests network scan outputs (nmap, netstat, arp, ping, traceroute, pcap), normalizes them, correlates related hosts, and provides interactive network topology visualization. The goal is fusing disparate network signals into a coherent graph of hosts, edges, and topology.

**Stack**: FastAPI + SQLite (async via aiosqlite) backend | React 18 + Vite + Cytoscape.js frontend
**Runtime**: Python 3.12, Node 18+
**Environment**: Nix dev shell (`nix develop`)

## Quick Reference

```bash
# Enter dev environment
nix develop

# Backend
nix develop -c bash -lc "cd backend && uvicorn main:app --reload"

# Frontend
nix develop -c bash -lc "cd frontend && npm run dev"

# Tests
nix develop -c .venv/bin/python -m pytest

# Python dependencies
cd backend && pip install -r requirements.txt

# Frontend dependencies
cd frontend && npm install
```

## Project Structure

```
backend/
  models/       # SQLAlchemy ORM (Host, Port, Connection, ARPEntry, RouteHop, RawImport, Conflict, User, AuthProvider, RoleMapping)
  auth/         # Authentication: jwt_service, oidc_service, dependencies, abac_stubs
  parsers/      # 6 data parsers (nmap, netstat, arp, ping, traceroute, pcap)
  routers/      # 13 API routers (hosts, imports, correlate, network, connections, arp, search, export, maintenance, vlans, updates, device_identities, auth)
  export_converters/  # Graph format exporters (GraphML, draw.io)
  services/     # Correlation engine, vendor lookup, data aging
  main.py       # FastAPI entry point
  database.py   # SQLAlchemy async setup + migrations
  schemas.py    # Pydantic models
  config.py     # Settings

frontend/
  src/pages/    # 11 pages (Dashboard, Hosts, Map, Import, Connections, ARP, Search, Config, HostDetail, Changelog, Login)
  src/components/  # NetworkMap (Cytoscape.js), HostTable, ProtectedRoute, UserMenu, etc.
  src/context/  # AuthContext provider
  src/api/client.js  # API client

tasks/          # Task tracking and lessons learned
docs/           # Architecture, backend, frontend, deployment docs
```

## Key Architecture Decisions

- **Async everything**: SQLAlchemy AsyncSession with aiosqlite throughout
- **Parser registry**: Auto-detection of input format (XML/grep/plain text) via `parsers/__init__.py`
- **Correlation engine**: IP → MAC → tag-based host merging with conflict detection
- **Visualization**: Cytoscape.js with compound nodes (VLAN→Subnet→Host), three layout modes (dagre/fcose/cola), device-type shapes/colors
- **Graph Export**: Network topology exportable to GraphML (Gephi/yEd) and draw.io (diagrams.net) via `/api/export/network/{format}`
- **Database**: SQLite with JSON columns for tags, source_types, conflict values
- **Authentication**: Multi-provider OIDC via authlib + local admin fallback. JWT (HS256) tokens. 3-tier RBAC (admin/editor/viewer) enforced via FastAPI `Depends()`. Feature flags (`AUTH_ENABLED`, `ENFORCE_AUTH`) for gradual rollout.

## Data Hygiene

- Never commit `.env`, `*.xml`, databases, pcaps, or binary artifacts
- Keep docs in `docs/` and top-level READMEs in sync with behavior changes

---

## Workflow Orchestration

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately – don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes – don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests – then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

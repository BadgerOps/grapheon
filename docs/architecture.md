# Architecture Overview

Graphēon is a FastAPI backend with a React frontend. It ingests multiple network data formats, normalizes them into a common schema, tags entities, and correlates them into a graph-like model. The repo standardizes on Python 3.12.

## Components

- Backend: FastAPI API server in `backend/` with SQLAlchemy async models and parser modules.
- Frontend: Vite + React SPA in `frontend/` that visualizes hosts, ports, connections, and ARP data.
- Database: SQLite database at `data/network.db` (ignored by git). Schema is created on startup.
- Parsers: Format-specific parsers in `backend/parsers/` (nmap, netstat, arp, ping, traceroute, pcap).

## Data Flow

1. Data arrives via raw text or file upload at `/api/import/*`.
2. The parser normalizes the payload into hosts, ports, connections, ARP entries, or traceroute hops.
3. Import pipeline upserts hosts and related records, and assigns tags (IP, MAC, port, service, subnet).
4. Correlation merges related hosts using tag similarity while guarding against conflicting MACs.
5. The frontend queries `/api/*` endpoints to render dashboards, tables, and the network graph.

## Environment Standard

- Python: 3.12.x via `nix develop` and `.python-version`.
- Node: managed by the Nix dev shell (currently Node 22).

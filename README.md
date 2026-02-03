# Graphēon

Graphēon ingests network scan outputs (nmap, netstat, arp, ping, traceroute, pcap), normalizes them, tags entities, and correlates related hosts. The stack is FastAPI + SQLite on the backend and Vite + React on the frontend. Python 3.12 is the standard runtime.

**Why Graphēon?** The name evokes graphing and mapping: this project fuses disparate network signals into a coherent graph of hosts, edges, and topology, which is exactly the product’s core purpose.

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

## Docs

See `docs/README.md` for architecture and workflow details.

## Data Hygiene

- Do not commit `.env` files or scan outputs like `*.xml`.
- Do not commit binary artifacts such as databases or pcaps.

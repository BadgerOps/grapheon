# Frontend

The Graphēon frontend is a Vite + React SPA in `frontend/`. Use the Nix dev shell for any npm command.

## Run Locally

```bash
nix develop -c bash -lc "cd frontend && npm install"
```

```bash
nix develop -c bash -lc "cd frontend && npm run dev"
```

The Vite dev server defaults to `http://localhost:5173` and proxies `/api` to the backend.

## Build

```bash
nix develop -c bash -lc "cd frontend && npm run build"
```

## Deployment

Cloudflare Pages deployments are driven by the GitHub `Deploy` workflow and the OpenTofu configuration in `terraform/`.

## App Structure

- `src/api/client.js` contains the API client.
- `src/components/` holds reusable UI components.
- `src/pages/` holds route-level pages.

# Release Process

Graphēon ships the backend and frontend as separate container images, and the passive agent as both a container image and a release artifact. Each component has its own semantic version.

## Version Sources

- Backend version: `backend/VERSION`
- Backend changelog: `backend/CHANGELOG.md`
- Frontend version: `frontend/package.json`
- Frontend changelog: `frontend/CHANGELOG.md`
- Agent version: `agent/VERSION`
- Agent changelog: `agent/CHANGELOG.md`

`CI` validates that each component's version matches the top entry in its changelog.

## Prepare a Release

1. Create a PR that updates the component version and its `CHANGELOG.md`.
2. Ensure the PR passes all CI checks.
3. Merge the PR to `master`.

## Auto-Release on Merge

On every push to `master`, the `Release Components` workflow:

- Reads `backend/VERSION`, `frontend/package.json`, and `agent/VERSION`.
- Checks whether `backend-vX.Y.Z`, `frontend-vX.Y.Z`, or `agent-vX.Y.Z` tags already exist.
- Creates tags/releases and pushes images only for components without tags.

The workflow builds and pushes:

- `ghcr.io/badgerops/grapheon-backend:latest`
- `ghcr.io/badgerops/grapheon-backend:vX.Y.Z`
- `ghcr.io/badgerops/grapheon-frontend:latest`
- `ghcr.io/badgerops/grapheon-frontend:vX.Y.Z`
- `ghcr.io/badgerops/grapheon-agent:latest`
- `ghcr.io/badgerops/grapheon-agent:vX.Y.Z`

For the passive agent, the workflow also:

- creates an `agent-vX.Y.Z` GitHub release
- uploads `grapheon-agent-vX.Y.Z.tar.gz` containing the runtime, install helper, systemd units, and quickstart docs
- uploads `grapheon-agent-vX.Y.Z.tar.gz.sha256` for checksum verification

## Notes

- See `docs/deployment.md` for the Docker container deployment guide.
- See `docs/agent_quickstart.md` for the passive agent bootstrap and deployment guide.
- See `docs/example_deployment.md` for the alternative NixOS + Podman + systemd deployment.
- The frontend includes an in-app changelog at `/changelog`.

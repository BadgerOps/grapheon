# Graphēon Passive Agent Runtime

This directory contains the current host-side runtime for issue `#48`.

Contents:

- `grapheon_agent.py` - stdlib-only one-shot collector and check-in client
- `tests/test_grapheon_agent.py` - unit tests for parsing and delta logic

## Design Notes

- Runtime model: one-shot process, intended to run from a `systemd` timer
- Identity: persistent random `agent_uuid`
- Bootstrap auth: enrollment key
- Steady-state auth: per-agent API key issued by Graphēon after approval
- Collection sources:
  - `ip -json addr show`
  - `ip -json neigh show`
  - `ip -json route show`
  - `ss -tunapH` with `netstat -tunap` fallback
- Transport: gzip-compressed JSON to `POST /api/agents/check-in`
- Delta mode: set-diff against the last successful local snapshot

The runtime keeps local state under `/var/lib/grapheon-agent` by default:

- `agent_uuid`
- `api_key`
- `state.json`

## Manual CLI Usage

The runtime can be invoked directly with flags from either a repo checkout or an installed host copy. It does not require `systemd` to run.

Distribution options:

- GitHub release artifact: `grapheon-agent-vX.Y.Z.tar.gz`
- Artifact checksum: `grapheon-agent-vX.Y.Z.tar.gz.sha256`
- GHCR image: `ghcr.io/badgerops/grapheon-agent:latest` and `:vX.Y.Z`

Examples:

```bash
python3 agent/grapheon_agent.py \
  --server-url https://grapheon.example.com \
  --enrollment-key gaek_replace_me \
  --state-dir ./agent-state \
  --register-only
```

```bash
python3 agent/grapheon_agent.py \
  --server-url https://grapheon.example.com \
  --state-dir ./agent-state \
  --force \
  --log-level DEBUG
```

```bash
/usr/bin/env python3 /opt/grapheon/agent/grapheon_agent.py \
  --config /etc/grapheon-agent.env \
  --force
```

```bash
docker run --rm \
  --network host \
  --pid host \
  -v "$PWD/agent-state:/var/lib/grapheon-agent" \
  --env-file ./grapheon-agent.env \
  ghcr.io/badgerops/grapheon-agent:latest \
  --register-only
```

Useful flags:

- `--register-only` registers or polls approval and exits without collecting
- `--check-in-only` requires an existing local API key and skips registration
- `--force` bypasses cached cadence gating for an immediate run
- `--state-dir` keeps manual runs isolated from the default `/var/lib/grapheon-agent`
- `--log-level DEBUG` makes parsing, registration, and check-in troubleshooting easier

Versioned install helpers:

- `scripts/install-passive-agent.sh`
- `scripts/upgrade-passive-agent.sh`
- `scripts/rollback-passive-agent.sh <version>`
- `scripts/uninstall-passive-agent.sh [--purge-state]`

`--help` output:

```text
usage: grapheon_agent.py [-h] [--config CONFIG] [--state-dir STATE_DIR]
                         [--server-url SERVER_URL]
                         [--enrollment-key ENROLLMENT_KEY]
                         [--display-name DISPLAY_NAME] [--site-name SITE_NAME]
                         [--hostname HOSTNAME]
                         [--request-timeout-seconds REQUEST_TIMEOUT_SECONDS]
                         [--timer-interval-seconds TIMER_INTERVAL_SECONDS]
                         [--api-key-header API_KEY_HEADER] [--ca-file CA_FILE]
                         [--insecure-skip-verify]
                         [--register-only | --check-in-only] [--force]
                         [--log-level LOG_LEVEL]

Low-impact one-shot passive collector for Graphēon.

The agent can run from a systemd timer or be invoked directly with flags for
manual registration, approval polling, and check-in.
```

See `docs/agent_quickstart.md` for the deployment walkthrough and `deploy/grapheon-agent.*` for the shipped `systemd` units.

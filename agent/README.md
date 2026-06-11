# Graphēon Passive Agent Runtime

This directory contains the current host-side runtime for issue `#48`.

Contents:

- `grapheon_agent.py` - stdlib-only one-shot collector and check-in client
- `tests/test_grapheon_agent.py` - unit tests for parsing and snapshot logic

## Design Notes

- Runtime model: short-lived collector process, supervised by a `systemd` timer/service
- Identity: persistent random `agent_uuid`
- Bootstrap auth: enrollment key
- Steady-state auth: per-agent API key issued by Graphēon after approval
- Collection sources:
  - `ip -json addr show`
  - `ip -json neigh show`
  - `ip -json route show`
  - `ss -tunapH` with `netstat -tunap` fallback
- Transport: gzip-compressed JSON to `POST /api/agents/check-in`
- Snapshot mode: sends full passive snapshots so the backend can mark missing agent-scoped observations stale/removed

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
/usr/bin/env python3 /opt/grapheon/agent/current/grapheon_agent.py \
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
- `--ignore-local-net` drops loopback/link-local IPs and common local virtualization bridge interfaces
- `--user-agent` overrides the default `Grapheon-Agent/<version> python-urllib` HTTP User-Agent sent to Graphēon
- `--log-level DEBUG` makes parsing, registration, and check-in troubleshooting easier

During normal timer execution, the agent performs a lightweight authenticated poll before local cadence gating. The shipped timer defaults to a 15-second control-plane poll cadence so admin-requested collections are picked up promptly. If an admin has requested an on-demand collection in Graphēon, the poll response causes that run to bypass the cached interval and send a fresh full snapshot.

Set `GRAPHEON_AGENT_IGNORE_LOCAL_NET=true` in `/etc/grapheon-agent.env` on workstation, hypervisor, or lab hosts where loopback, link-local IPv6, and local virtualization bridge interfaces such as `vmnet*`, `vboxnet*`, `docker*`, or `virbr*` would otherwise add noisy host-local observations. Normal LAN/private addresses on physical or primary interfaces are still collected.

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
                         [--api-key-header API_KEY_HEADER]
                         [--user-agent USER_AGENT] [--ignore-local-net]
                         [--ca-file CA_FILE] [--insecure-skip-verify]
                         [--register-only | --check-in-only] [--force]
                         [--log-level LOG_LEVEL]

Low-impact one-shot passive collector for Graphēon.

The agent can run from a systemd timer or be invoked directly with flags for
manual registration, approval polling, and check-in.
```

## Registration Troubleshooting

The first-run log line `No agent API key found; registering agent <agent_uuid>` is normal. The local API key is the per-agent secret that Graphēon issues after registration or approval and stores at `/var/lib/grapheon-agent/api_key`; it is different from the enrollment key in `/etc/grapheon-agent.env`.

If registration fails with `HTTP 403 calling api/agents/register: error code: 1010`, the request was rejected before the Graphēon backend handled the enrollment key. Check the edge proxy, bot protection, browser-integrity checks, or WAF policy in front of Graphēon. Allow the agent host/IP or bypass those checks for `/api/agents/*`.

The agent sends a deterministic User-Agent header by default:

```text
Grapheon-Agent/<version> python-urllib
```

Override it when needed with `GRAPHEON_AGENT_USER_AGENT` in `/etc/grapheon-agent.env` or with `--user-agent` for direct runs.

See `docs/agent_quickstart.md` for the deployment walkthrough and `deploy/grapheon-agent.*` for the shipped `systemd` units.

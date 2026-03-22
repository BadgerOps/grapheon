# Agent Quickstart

This guide walks through the current passive-agent runtime shipped in this repo.

It covers:

1. Creating a passive collection policy
2. Creating an enrollment key
3. Running the agent manually with flags
4. Installing the one-shot collector and `systemd` timer
5. Starting the agent for registration
6. Approving the pending agent
7. Starting the agent again to obtain the per-agent API key and send the first check-in
8. Enabling the timer for ongoing passive collection

## What The Runtime Does

The shipped runtime is:

- `agent/grapheon_agent.py`
- `agent/Dockerfile`
- `deploy/grapheon-agent.service`
- `deploy/grapheon-agent.timer`
- `deploy/grapheon-agent.env.example`
- `scripts/install-passive-agent.sh`

Behavior:

- generates and persists a random `agent_uuid`
- registers outbound with an enrollment key
- waits for approval if the key is not auto-approved
- stores the issued per-agent API key locally
- collects passive local data only:
  - `ip -json addr show`
  - `ip -json neigh show`
  - `ip -json route show`
  - `ss -tunapH` with `netstat -tunap` fallback
- sends gzip-compressed JSON deltas over HTTPS

The passive agent is also published as:

- GitHub release artifact: `grapheon-agent-vX.Y.Z.tar.gz`
- GHCR image: `ghcr.io/badgerops/grapheon-agent:latest` and `:vX.Y.Z`

## Prerequisites

- Graphēon backend running
- An admin account
- Linux host with:
  - Python 3
  - `systemd`
  - `ip`
  - `ss` or `netstat`
- `curl`
- `jq`

For local Graphēon development:

```bash
nix develop -c bash -lc "cd backend && uvicorn main:app --reload"
```

## 1. Log In As Admin

Get a JWT:

```bash
export GRAPH_URL="http://localhost:8000"

export TOKEN="$(
  curl -sS \
    -X POST "$GRAPH_URL/api/auth/login/local" \
    -H "Content-Type: application/json" \
    -d '{
      "username": "admin",
      "password": "changeme"
    }' | jq -r '.access_token'
)"
```

## 2. Create A Passive Collection Policy

This example keeps the collector gentle:

```bash
export POLICY_ID="$(
  curl -sS \
    -X POST "$GRAPH_URL/api/agents/policies" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "default-passive-hourly",
      "description": "Hourly passive collection with low impact defaults",
      "checkin_interval_seconds": 3600,
      "jitter_seconds": 300,
      "command_timeout_seconds": 15,
      "enabled_commands": {
        "ip_neigh": true,
        "ss_tunap": true,
        "ip_addr": true,
        "ip_route": true
      },
      "max_report_bytes": 262144,
      "is_active": true
    }' | jq -r '.id'
)"
```

## 3. Create An Enrollment Key

This example requires approval:

```bash
ENROLLMENT_JSON="$(
  curl -sS \
    -X POST "$GRAPH_URL/api/agents/enrollment-keys" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
      \"name\": \"branch-rollout-1\",
      \"description\": \"Manual approval for first branch rollout\",
      \"default_policy_id\": $POLICY_ID,
      \"auto_approve\": false,
      \"is_active\": true,
      \"max_registrations\": 50
    }"
)"

export ENROLLMENT_KEY="$(printf '%s' "$ENROLLMENT_JSON" | jq -r '.enrollment_key')"
```

Important: the raw enrollment key is returned once. Store it in your secret-management flow.

## 4. Run The Agent Manually With Flags

The runtime is not limited to `systemd`. You can run it directly from a repo checkout or from the installed host copy.

Register or poll approval without collecting:

```bash
python3 agent/grapheon_agent.py \
  --server-url "$GRAPH_URL" \
  --enrollment-key "$ENROLLMENT_KEY" \
  --state-dir ./agent-state \
  --display-name "Branch Router 01" \
  --site-name "Boise" \
  --register-only \
  --log-level INFO
```

After approval, force an immediate direct check-in:

```bash
python3 agent/grapheon_agent.py \
  --server-url "$GRAPH_URL" \
  --enrollment-key "$ENROLLMENT_KEY" \
  --state-dir ./agent-state \
  --force \
  --log-level DEBUG
```

If the local API key already exists and you want to skip registration entirely:

```bash
python3 agent/grapheon_agent.py \
  --server-url "$GRAPH_URL" \
  --state-dir ./agent-state \
  --check-in-only \
  --force
```

Show built-in CLI help:

```bash
python3 agent/grapheon_agent.py --help
```

Relevant flags:

- `--register-only` registers or polls approval and exits before collection
- `--check-in-only` requires an existing local API key and skips registration
- `--force` bypasses cached cadence gating
- `--state-dir` isolates local agent state for testing or manual runs
- `--config` loads the same env-style settings used by the installed `systemd` unit

The help output includes these manual examples:

```text
Low-impact one-shot passive collector for Graphēon.

The agent can run from a systemd timer or be invoked directly with flags for
manual registration, approval polling, and check-in.

Examples:
  Register or poll approval directly from a repo checkout:
    python3 agent/grapheon_agent.py --server-url https://grapheon.example.com --enrollment-key gaek_xxx --state-dir ./agent-state --register-only
```

## 5. Install The Runtime On The Target Host

You can install from either:

- a repo checkout
- the versioned GitHub release tarball `grapheon-agent-vX.Y.Z.tar.gz`

From the release artifact:

```bash
tar -xzf grapheon-agent-vX.Y.Z.tar.gz
cd grapheon-agent-vX.Y.Z
sudo bash scripts/install-passive-agent.sh
```

From the repo checkout on the target host:

```bash
sudo bash scripts/install-passive-agent.sh
```

This installs:

- `/opt/grapheon/agent/grapheon_agent.py`
- `/etc/systemd/system/grapheon-agent.service`
- `/etc/systemd/system/grapheon-agent.timer`
- `/etc/grapheon-agent.env` if it does not already exist
- `/var/lib/grapheon-agent`

Optional containerized run instead of a host install:

```bash
docker run --rm \
  --network host \
  --pid host \
  -v "$PWD/agent-state:/var/lib/grapheon-agent" \
  --env-file ./grapheon-agent.env \
  ghcr.io/badgerops/grapheon-agent:latest \
  --register-only
```

## 6. Configure The Agent Environment

Edit `/etc/grapheon-agent.env`:

```bash
sudo editor /etc/grapheon-agent.env
```

Minimum configuration:

```dotenv
GRAPHEON_AGENT_SERVER_URL=https://grapheon.example.com
GRAPHEON_AGENT_ENROLLMENT_KEY=gaek_replace_me
GRAPHEON_AGENT_DISPLAY_NAME=Branch Router 01
GRAPHEON_AGENT_SITE_NAME=Boise
```

For local development over plain HTTP:

```dotenv
GRAPHEON_AGENT_SERVER_URL=http://localhost:8000
```

The runtime stores local state under `/var/lib/grapheon-agent`:

- `agent_uuid`
- `api_key`
- `state.json`

## 7. Start The Agent Once For Registration

Run the one-shot service manually:

```bash
sudo systemctl start grapheon-agent.service
sudo systemctl status grapheon-agent.service --no-pager
```

On first run with a non-auto-approved enrollment key, the runtime will:

- generate and persist `agent_uuid`
- register with Graphēon
- exit cleanly in `pending` state

## 8. Review And Approve The Pending Agent

List pending agents:

```bash
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  "$GRAPH_URL/api/agents?enrollment_state=pending" | jq
```

Approve the agent:

```bash
export AGENT_ID="$(
  curl -sS \
    -H "Authorization: Bearer $TOKEN" \
    "$GRAPH_URL/api/agents?enrollment_state=pending" | jq -r '.items[0].id'
)"

curl -sS \
  -X POST "$GRAPH_URL/api/agents/$AGENT_ID/approve" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"policy_id\": $POLICY_ID
  }" | jq
```

## 9. Start The Agent Again To Receive Its API Key

Run the one-shot service again:

```bash
sudo systemctl start grapheon-agent.service
sudo systemctl status grapheon-agent.service --no-pager
```

On this run the runtime will:

- re-register using the enrollment key
- receive its one-time per-agent API key
- store that key at `/var/lib/grapheon-agent/api_key`
- collect passive local observations
- send the first gzip-compressed check-in

Verify local state:

```bash
sudo ls -l /var/lib/grapheon-agent
sudo cat /var/lib/grapheon-agent/agent_uuid
```

## 10. Verify In Graphēon

Inspect the agent:

```bash
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  "$GRAPH_URL/api/agents/$AGENT_ID" | jq
```

Inspect check-ins:

```bash
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  "$GRAPH_URL/api/agents/$AGENT_ID/checkins" | jq
```

You should see:

- `enrollment_state` set to `active`
- a populated `api_key_prefix`
- `last_seen_at`
- check-in history entries with `auth_method: "api_key"`

## 11. Enable Periodic Collection

Enable the timer:

```bash
sudo systemctl enable --now grapheon-agent.timer
sudo systemctl list-timers grapheon-agent.timer
```

The shipped timer runs every 15 minutes. The runtime uses the cached backend policy to decide whether a full collection should happen on that invocation. This allows:

- simple static `systemd` units
- server-controlled interval policy
- server-controlled jitter
- server-controlled command enable/disable

If the cached policy interval has not elapsed yet, the runtime exits quickly.

## Operational Notes

- Do not derive `agent_uuid` from MAC addresses.
- Treat the enrollment key as bootstrap-only.
- Treat `/var/lib/grapheon-agent/api_key` as a secret.
- Prefer `auto_approve=false` for real deployments.
- The current delta mode only sends additive/update observations; removals are not represented yet.
- No active scanning is performed in the MVP.

## Troubleshooting

View recent service logs:

```bash
sudo journalctl -u grapheon-agent.service -n 100 --no-pager
```

Force an immediate run:

```bash
sudo systemctl start grapheon-agent.service
```

Run the collector directly:

```bash
sudo /usr/bin/env python3 /opt/grapheon/agent/grapheon_agent.py --force --log-level DEBUG
```

If the agent was approved but the API key file was lost, rotate the key from the admin API and place the new secret back on the host:

```bash
ROTATE_JSON="$(
  curl -sS \
    -X POST "$GRAPH_URL/api/agents/$AGENT_ID/rotate-api-key" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "reason": "lost local api_key file"
    }'
)"

export NEW_AGENT_API_KEY="$(printf '%s' "$ROTATE_JSON" | jq -r '.api_key')"
printf '%s\n' "$NEW_AGENT_API_KEY" | sudo tee /var/lib/grapheon-agent/api_key >/dev/null
sudo chmod 600 /var/lib/grapheon-agent/api_key
sudo systemctl start grapheon-agent.service
```

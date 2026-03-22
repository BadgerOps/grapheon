# Agent Quickstart

This guide walks through the current passive-agent MVP using the API surface that exists today.

It covers:

1. Creating a passive collection policy
2. Creating an enrollment key
3. Registering a new agent
4. Approving the agent
5. Obtaining the per-agent API key
6. Sending a passive check-in

## Prerequisites

- Graphēon backend running
- An admin account
- `curl`
- `jq`
- A host where you can persist agent state locally

For local development:

```bash
nix develop -c bash -lc "cd backend && uvicorn main:app --reload"
```

## 1. Log In As Admin

Get a JWT from the local admin login endpoint:

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

## 2. Create A Passive Agent Policy

This example keeps the command set small and the cadence gentle:

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

This key allows agents to bootstrap into a `pending` state that requires admin approval:

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

Important: the raw enrollment key is only returned once. Store it in your secret-management flow.

## 4. Generate And Persist `agent_uuid`

Do this once on the host. Do not derive it from MAC addresses.

```bash
sudo install -d -m 0700 /var/lib/grapheon-agent
test -f /var/lib/grapheon-agent/agent_uuid || uuidgen | sudo tee /var/lib/grapheon-agent/agent_uuid >/dev/null
export AGENT_UUID="$(sudo cat /var/lib/grapheon-agent/agent_uuid)"
```

## 5. Register The Agent

Send a bootstrap registration request with basic host metadata:

```bash
REGISTER_JSON="$(
  curl -sS \
    -X POST "$GRAPH_URL/api/agents/register" \
    -H "Content-Type: application/json" \
    -d "{
      \"enrollment_key\": \"$ENROLLMENT_KEY\",
      \"agent_uuid\": \"$AGENT_UUID\",
      \"display_name\": \"Branch Router 01\",
      \"hostname\": \"branch-router-01\",
      \"site_name\": \"Boise\",
      \"agent_version\": \"0.1.0\",
      \"platform\": \"linux\",
      \"platform_release\": \"6.12\",
      \"addresses\": [
        {
          \"ip_address\": \"10.20.0.5\",
          \"interface\": \"eth0\",
          \"prefix_length\": 24,
          \"mac_address\": \"AA:BB:CC:DD:EE:01\"
        }
      ]
    }"
)"

printf '%s\n' "$REGISTER_JSON" | jq
```

Expected result with `auto_approve=false`:

- `status` is `pending`
- `approval_required` is `true`
- no `api_key` is returned yet

## 6. Review And Approve The Agent

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

## 7. Re-Register To Receive The Per-Agent API Key

After approval, call the same registration endpoint again:

```bash
REGISTER_ACTIVE_JSON="$(
  curl -sS \
    -X POST "$GRAPH_URL/api/agents/register" \
    -H "Content-Type: application/json" \
    -d "{
      \"enrollment_key\": \"$ENROLLMENT_KEY\",
      \"agent_uuid\": \"$AGENT_UUID\",
      \"display_name\": \"Branch Router 01\",
      \"hostname\": \"branch-router-01\",
      \"site_name\": \"Boise\",
      \"agent_version\": \"0.1.0\",
      \"platform\": \"linux\",
      \"platform_release\": \"6.12\",
      \"addresses\": [
        {
          \"ip_address\": \"10.20.0.5\",
          \"interface\": \"eth0\",
          \"prefix_length\": 24,
          \"mac_address\": \"AA:BB:CC:DD:EE:01\"
        }
      ]
    }"
)"

export AGENT_API_KEY="$(printf '%s' "$REGISTER_ACTIVE_JSON" | jq -r '.api_key')"
```

Important: the per-agent API key is only returned when it is first issued. Persist it locally on the host, for example:

```bash
printf '%s\n' "$AGENT_API_KEY" | sudo tee /var/lib/grapheon-agent/api_key >/dev/null
sudo chmod 0600 /var/lib/grapheon-agent/api_key
```

## 8. Send A Passive Check-In

The current backend expects a normalized JSON payload. This example sends one manually.

Create a payload:

```bash
cat >/tmp/grapheon-agent-report.json <<EOF
{
  "agent_uuid": "$AGENT_UUID",
  "observed_at": "2026-03-22T18:00:00Z",
  "sequence_number": 1,
  "full_snapshot": false,
  "hostname": "branch-router-01",
  "agent_version": "0.1.0",
  "platform": "linux",
  "platform_release": "6.12",
  "metadata": {
    "collector": "manual-quickstart"
  },
  "addresses": [
    {
      "ip_address": "10.20.0.5",
      "interface": "eth0",
      "prefix_length": 24,
      "mac_address": "AA:BB:CC:DD:EE:01"
    }
  ],
  "neighbors": [
    {
      "ip_address": "10.20.0.1",
      "mac_address": "11:22:33:44:55:66",
      "interface": "eth0",
      "state": "reachable"
    }
  ],
  "connections": [
    {
      "local_ip": "10.20.0.5",
      "local_port": 443,
      "remote_ip": "10.20.0.10",
      "remote_port": 51514,
      "protocol": "tcp",
      "state": "established",
      "pid": 777,
      "process_name": "python"
    }
  ],
  "routes": [
    {
      "destination": "default",
      "gateway": "10.20.0.1",
      "interface": "eth0",
      "source_ip": "10.20.0.5"
    }
  ]
}
EOF
```

Send it with gzip compression:

```bash
gzip -c /tmp/grapheon-agent-report.json >/tmp/grapheon-agent-report.json.gz

curl -sS \
  -X POST "$GRAPH_URL/api/agents/check-in" \
  -H "Content-Type: application/json" \
  -H "Content-Encoding: gzip" \
  -H "X-Agent-Api-Key: $AGENT_API_KEY" \
  --data-binary @/tmp/grapheon-agent-report.json.gz | jq
```

Expected result:

- `status` is `accepted`
- `summary.hosts_created`, `summary.arp_entries_created`, and `summary.connections_created` reflect the ingest result
- the response includes the resolved policy and check-in audit metadata

## 9. Verify In The Admin API

List the agent:

```bash
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  "$GRAPH_URL/api/agents/$AGENT_ID" | jq
```

List check-ins:

```bash
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  "$GRAPH_URL/api/agents/$AGENT_ID/checkins" | jq
```

## Operational Notes

- Keep `agent_uuid` and the per-agent API key on disk with restrictive permissions.
- Treat the enrollment key as a bootstrap secret only.
- Prefer `auto_approve=false` for real rollouts.
- Do not run active scanning commands in the agent MVP.
- A future packaged agent can replace the manual JSON payload with normalized output from local commands.

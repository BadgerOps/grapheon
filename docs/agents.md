# Passive Agents

Graphēon now has the backend foundation for a low-impact passive agent fleet. The MVP stays intentionally conservative: outbound-only check-in, no active scanning, slow cadence, and reuse of Graphēon's existing host, ARP, connection, and import models.

For a concrete API walkthrough, see `docs/agent_quickstart.md`.

## MVP Shape

- Runtime model: one-shot collector plus `systemd` timer on the managed host.
- Collection model: local/passive commands only such as `ip neigh`, `ss -tunap`, `ip addr`, and `ip route`.
- Transport model: compressed JSON reports over HTTPS with outbound-only check-in.
- Backend model: agent registry, enrollment keys, approval workflow, policy profiles, check-in audit records, and normalized ingest into existing Graphēon tables.

## Identity Model

Use two separate values:

- `agent_uuid`: random, generated once by the agent on first run and persisted locally
- API keys: opaque shared secrets used only for authentication

Do not derive `agent_uuid` from MAC addresses or other host traits. MACs are operational metadata and can change or be duplicated. `agent_uuid` should be stable independent of NIC replacement, VM cloning cleanup, or interface layout.

## Current Backend Endpoints

- `GET /api/agents` - List enrolled agents and last-seen state.
- `POST /api/agents` - Create an agent record manually as an admin.
- `GET /api/agents/{id}` - Get one enrolled agent.
- `PATCH /api/agents/{id}` - Update agent registry metadata or policy assignment.
- `POST /api/agents/{id}/approve` - Approve a pending agent.
- `POST /api/agents/{id}/reject` - Reject a pending agent.
- `GET /api/agents/{id}/checkins` - List check-in history for one agent.
- `GET /api/agents/policies` - List passive collection policies.
- `POST /api/agents/policies` - Create a passive collection policy.
- `PATCH /api/agents/policies/{id}` - Update a passive collection policy.
- `GET /api/agents/enrollment-keys` - List enrollment keys.
- `POST /api/agents/enrollment-keys` - Create an enrollment key and return the secret once.
- `PATCH /api/agents/enrollment-keys/{id}` - Update an enrollment key.
- `POST /api/agents/register` - Bootstrap or re-poll agent registration with an enrollment key.
- `POST /api/agents/check-in` - Agent report ingest endpoint using the per-agent API key.

Read endpoints use the existing viewer/editor/admin auth model. Enrollment-key and check-in endpoints are for machine-to-machine traffic.

## Enrollment Flow

The current MVP enrollment flow is:

1. An admin creates an enrollment key in the UI or API.
2. The agent generates and stores a random `agent_uuid` locally.
3. The agent calls `POST /api/agents/register` with:
   - the enrollment key
   - `agent_uuid`
   - hostname, platform, version
   - local interface IP/MAC summary
4. The backend creates or updates an agent record.
5. If the enrollment key has `auto_approve=false`, the agent remains `pending` until an admin approves it in the UI.
6. Once approved, the agent re-calls `POST /api/agents/register`.
7. The backend returns a one-time per-agent API key.
8. The agent stores that per-agent API key and uses it for future `POST /api/agents/check-in` calls.

This keeps bootstrap easy for operators while avoiding a single long-lived fleet-wide shared secret for steady-state operation.

## Enrollment Key Model

Each enrollment key supports:

- `name`
- `description`
- `default_policy_id`
- `auto_approve`
- `is_active`
- `expires_at`
- `max_registrations`
- `registration_count`

Recommended default is `auto_approve=false` unless you fully trust the environment where the key will be deployed.

## Policy Model

Each policy captures low-impact collection controls:

- `checkin_interval_seconds`
- `jitter_seconds`
- `command_timeout_seconds`
- `enabled_commands`
- `max_report_bytes`

The command set is explicitly limited in the MVP:

- `ip_neigh`
- `ss_tunap`
- `ip_addr`
- `ip_route`

This keeps the agent side easy to reason about and avoids unexpected CPU or network load.

## Report Model

The ingest endpoint currently expects a normalized JSON payload. That keeps server-side ingest useful before Graphēon ships a packaged collector that converts raw command output into a stable schema.

The payload includes:

- Agent identity and sequence metadata
- Local interface addresses
- Neighbor observations
- Local socket observations
- Route observations
- Optional host/platform metadata

Reports may be sent with `Content-Encoding: gzip`. The backend stores the normalized payload in both:

- `agent_checkins` for operational history
- `raw_imports` for auditability and future replay/converter work

The ingest path upserts:

- `hosts`
- `arp_entries`
- `connections`

No automatic correlation run is triggered on every check-in in the MVP. That keeps steady-state ingest cheap. Operators can still run the existing correlation workflow separately.

## Authentication Notes

- Enrollment keys are admin-created bootstrap secrets.
- Enrollment keys are stored hashed server-side.
- Per-agent API keys are distinct from enrollment keys.
- Per-agent API keys are stored hashed server-side.
- `agent_uuid` is the durable agent identity.
- API keys authenticate the caller but do not define identity.

The backend verifies:

1. The presented agent API key matches an approved agent record.
2. The report `agent_uuid` matches that authenticated agent.

## What This Slice Does Not Yet Do

- Package or ship the actual host-side collector/service
- Parse raw `ip neigh` or `ss` output on the server
- Rotate per-agent API keys through the agent protocol
- Surface fleet views in the frontend
- Issue client certificates or require mTLS for agents

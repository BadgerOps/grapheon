# Passive Agents

Graphēon now has the backend foundation and the first host-side runtime for a low-impact passive agent fleet. The MVP stays intentionally conservative: outbound-only check-in, no active scanning, bounded passive observation windows, slow cadence, and reuse of Graphēon's existing host, ARP, connection, and import models.

For a concrete runtime walkthrough, see `docs/agent_quickstart.md`. For host-side implementation notes, see `agent/README.md`.

## MVP Shape

- Runtime model: short-lived collector plus `systemd` timer/service on the managed host.
- Collection model: local/passive commands only such as `ip neigh`, `ss -tunap`, `ip addr`, `ip route`, optional normalized topology evidence files, and explicitly requested bounded tcpdump observation windows.
- Transport model: compressed JSON reports over HTTPS with outbound-only check-in.
- Backend model: agent registry, enrollment keys, approval workflow, policy profiles, check-in audit records, and normalized ingest into existing Graphēon tables.

## Identity Model

Use two separate values:

- `agent_uuid`: random, generated once by the agent on first run and persisted locally
- API keys: opaque shared secrets used only for authentication

Do not derive `agent_uuid` from MAC addresses or other host traits. MACs are operational metadata and can change or be duplicated. `agent_uuid` should be stable independent of NIC replacement, VM cloning cleanup, or interface layout.

## Current API Endpoints

- `GET /api/agents` - List enrolled agents and last-seen state.
- `POST /api/agents` - Create an agent record manually as an admin.
- `GET /api/agents/{id}` - Get one enrolled agent.
- `PATCH /api/agents/{id}` - Update agent registry metadata or policy assignment.
- `POST /api/agents/{id}/approve` - Approve a pending agent.
- `POST /api/agents/{id}/reject` - Reject a pending agent.
- `POST /api/agents/{id}/revoke` - Revoke an agent and invalidate its API key.
- `POST /api/agents/{id}/reactivate` - Move a revoked or inactive agent back to pending approval.
- `POST /api/agents/{id}/rotate-api-key` - Rotate and reissue a per-agent API key once.
- `POST /api/agents/{id}/request-collection` - Request that an active agent collect on its next timer run, optionally including passive capture options for a bounded tcpdump observation window.
- `GET /api/agents/{id}/checkins` - List check-in history for one agent.
- `GET /api/agents/{id}/observations` - List current or historical observations for one agent, with optional `observation_type`, `observation_role`, `min_confidence`, and `is_current` filters.
- `POST /api/agents/poll` - Agent-authenticated control-plane poll for policy and pending collection requests.
- `GET /api/agents/policies` - List passive collection policies.
- `POST /api/agents/policies` - Create a passive collection policy.
- `PATCH /api/agents/policies/{id}` - Update a passive collection policy.
- `GET /api/agents/enrollment-keys` - List enrollment keys.
- `POST /api/agents/enrollment-keys` - Create an enrollment key and return the secret once.
- `PATCH /api/agents/enrollment-keys/{id}` - Update an enrollment key.
- `POST /api/agents/register` - Bootstrap or re-poll agent registration with an enrollment key.
- `POST /api/agents/check-in` - Agent report ingest endpoint using the per-agent API key.

Agent management read and write endpoints require admin access because they expose hostnames, IP addresses, MAC addresses, policy assignments, and operational check-in history. Enrollment-key and check-in endpoints are for machine-to-machine traffic.

## Frontend Operations View

Admins can now manage passive agents directly in the SPA at `/agents`. The page provides:

- fleet status with approval state and last-seen health
- per-agent detail and recent check-in history
- policy profile creation and updates
- enrollment-key creation and updates
- approval, rejection, revocation, reactivation, policy reassignment, and API-key rotation actions

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
- `topology_evidence`

This keeps the agent side easy to reason about and avoids unexpected CPU or network load.

On-demand requests can include `passive_capture` options with `enabled`, `duration_seconds` capped at 300, `max_bytes`, optional `interfaces`, and `include_flows`. These options tell the agent to run a local bounded tcpdump observation window on its next poll. If interfaces are not provided, the agent uses the interface or interfaces that own default routes rather than tcpdump's `any` pseudo-device, because the topology filter needs Ethernet headers. The agent skips cadence and jitter for requested collections, parses the temporary pcap into normalized topology evidence, deletes the pcap, and sends only summaries.

The passive tcpdump parser is map-focused. It extracts VLAN IDs, LLDP/CDP metadata, DHCPv4/DHCPv6 lease and option hints, IPv6 router-advertisement prefixes and DNS options, DNS/mDNS/LLMNR/NBNS names, SSDP and WS-Discovery service labels, STP/LACP L2 hints, HSRP/VRRP/CARP gateway hints, visible OSPF/RIP/EIGRP/BGP routing hints, and aggregated optional flow headers. It does not parse TLS SNI, HTTP Host, QUIC SNI, Kerberos, LDAP, or SMB names.

Network Map evidence can be inspected as current-only by default or with historical/stale evidence included. Selecting evidence-backed map elements shows the source, observer, confidence, current/stale state, timestamps, and map summary. Operators can promote selected DNS evidence to a hostname, attach a selected host to an existing device identity, mark a selected network segment as expected, or ignore a noisy evidence source/observer for the current map view without deleting stored evidence.

## Report Model

The ingest endpoint expects a normalized JSON payload. The current host-side runtime converts local command output into that schema and sends gzip-compressed reports.

The payload includes:

- Agent identity and sequence metadata
- Local interface addresses
- Neighbor observations
- Local socket observations
- Route observations
- Optional topology evidence observations
- Optional host/platform metadata

Reports may be sent with `Content-Encoding: gzip`. The backend stores the normalized payload in both:

- `agent_checkins` for operational history
- `raw_imports` for auditability and future replay/converter work

Agent check-ins are stored with `source_origin=agent`. Manual paste/file/bulk imports use `source_origin=manual`. Host, port, ARP, connection, and import list APIs can filter by this origin so operator views can separate passive-agent data from manually imported data.

Successful check-ins write audit details for the number of observations created, refreshed, reactivated, marked stale, or explicitly removed, plus entity evidence created/refreshed counts. A missing record in a later full snapshot is treated as stale historical evidence, not as a delete request.

Agent ingest also tracks the collector separately from what it observed:

- `source_origin=agent` answers how the row entered Graphēon.
- `observed_by_agent_ids` / `observer_agent_id` answer which collector saw the row.
- `observation_role` answers what the row meant from that collector's vantage point, such as `agent_self_interface`, `arp_neighbor`, `connection_local`, `connection_remote`, or `route_gateway`.
- `confidence` is a 0-100 score used by APIs and map filters to distinguish strong self-interface evidence from weaker remote-only observations.

Agent-local interface addresses are high-confidence self observations and may carry the agent hostname. ARP neighbors, route gateways, and connection-only remote IPs are observed entities and are not labeled as the collector just because the collector saw them.

Agent ingest also writes host identity facts into `entity_evidence`. Evidence rows keep the observed field value, source origin/type, observing agent, raw import, agent observation, relationship type, confidence, first/last seen timestamps, and current/historical state. Host detail responses include these evidence rows so operators can inspect why a label, vendor, or device type exists without treating low-confidence observations as verified identity.

Canonical host fields are updated conservatively from evidence. Empty agent-only hostname, vendor, and device-type fields can be filled from current evidence, but verified hosts and existing manual-origin values are not overwritten by lower-confidence agent observations.

The ingest path upserts:

- `hosts`
- `arp_entries`
- `connections`

No automatic correlation run is triggered on every check-in in the MVP. That keeps steady-state ingest cheap. Operators can still run the existing correlation workflow separately.

The network map can derive optional agent topology layers from current observations:

- collector to local interface
- local interface to ARP neighbor
- local interface to connection remote
- route source to gateway

`GET /api/network/map` supports `observed_by_agent_id`, repeated `relationship_types`, `min_confidence`, and `include_collector_nodes` for these layers.

The map also uses current agent address prefixes, route destinations, configured VLAN CIDRs, and operator-provided `network_cidrs` hints as network boundaries. For example, a collector interface observed as `192.168.224.172/23` groups both `192.168.224.x` and `192.168.225.x` hosts under `192.168.224.0/23`. If no observed or configured CIDR covers a host, the map marks it as unresolved instead of assigning a hard-coded subnet.

## Runtime Notes

The shipped runtime lives in `agent/grapheon_agent.py` and is designed to be run from `deploy/grapheon-agent.service` and `deploy/grapheon-agent.timer`.

Current behavior:

- stores `agent_uuid`, API key, and cached state locally
- registers with an enrollment key until approved
- re-registers once approved to receive the per-agent API key
- supports direct manual execution with CLI flags in addition to the shipped `systemd` units
- polls Graphēon on each timer run before local cadence gating so admin-requested collections can run on the next outbound agent invocation
- uses a shipped 15-second timer cadence for lightweight control-plane polls while backend policy controls full collection frequency
- can optionally filter host-local network noise with `GRAPHEON_AGENT_IGNORE_LOCAL_NET=true`, dropping loopback/link-local IPs and common local virtualization bridge interfaces while keeping normal LAN/private addresses on primary interfaces
- can optionally run bounded passive tcpdump observation windows when configured or explicitly requested by an admin; raw pcaps are deleted locally and are not uploaded
- ships as both a GHCR container image and a GitHub release tarball for distribution
- installs host releases under a versioned `releases/` directory with a stable `current` symlink for rollback
- uses cached backend policy for:
  - `checkin_interval_seconds`
  - `jitter_seconds`
  - `command_timeout_seconds`
  - `enabled_commands`
- sends full passive snapshots after local collection
- still sends a heartbeat check-in even when no entries are observed, using empty snapshot arrays

Backend snapshot handling:

- missing entries in a later full snapshot are marked stale in backend agent-scoped observation state
- stale observations and linked evidence are retained as historical records; they are not deleted or marked removed unless an explicit removal path is used
- full report bodies in `agent_checkins.report` are retained only for the configured maintenance retention window
- cleanup preserves check-in metadata, summaries, raw import links, and agent-scoped observation state after pruning old report bodies

## Authentication Notes

- Enrollment keys are admin-created bootstrap secrets.
- Enrollment keys are stored hashed server-side.
- Per-agent API keys are distinct from enrollment keys.
- Per-agent API keys are stored hashed server-side.
- Admins can rotate a per-agent API key and receive the new raw secret once.
- Admins can revoke an agent, which clears the stored API-key hash and prevents old-key check-ins.
- Revoked or inactive agents must be reactivated back to pending approval before they can receive a new key through the normal registration polling flow.
- `agent_uuid` is the durable agent identity.
- API keys authenticate the caller but do not define identity.

The backend verifies:

1. The presented agent API key matches an approved agent record.
2. The report `agent_uuid` matches that authenticated agent.

## What This Slice Does Not Yet Do

- Parse raw `ip neigh` or `ss` output on the server
- Issue client certificates or require mTLS for agents

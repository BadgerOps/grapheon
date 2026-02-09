# Graphēon — Current Tasks

## Completed: Visualization Improvement — Phase 1 + Phase 2 + Phase 3

Goal: Accurate data, VLAN/segment-based grouping, connected entity visibility in the network map.

### Phase 1 — Data Accuracy Fixes ✅

- [x] **Fix ARP parser MAC cleaning**: Fixed `detect_format()` misclassifying Linux `?`-prefixed lines as macOS; added `[ether]` stripping to `_normalize_mac()`
- [x] **Migration: clean existing MACs**: Created and ran `backend/scripts/clean_mac_addresses.py` — cleaned 31 host MACs + 37 ARP entry MACs
- [x] **Nmap parser**: Parser code was correct; the nmap.xml lacked hostname/OS data (scan ran without -O/-A flags). No code change needed — documented as data gap.
- [x] **Auto-detect gateway/router**: Migration script identified MAC `78:45:58:8a:b7:5b` appearing as `.1` on 3 subnets → set `device_type=router`, `vendor=Ubiquiti` on 3 host records
- [x] **Run vendor lookups**: Full IEEE OUI database (38,437 entries) via mac-vendor-lookup. 10 real vendors resolved, 21 Tailscale/VPN MACs flagged as "Locally Administered"
- [x] **Verify**: Zero dirty MACs remain; 3 routers detected; all MAC vendors populated

### Phase 2 — Segment-Aware Visualization ✅

- [x] **Derive segments from ARP interfaces**: `/api/network/map` now accepts `group_by=segment` parameter, builds IP→interface mapping from ARP table at query time
- [x] **Update `/api/network/map` endpoint**: Added segment grouping with `subnet_hint`, `_get_segment_color()`, and `is_gateway` flag on router nodes
- [x] **Frontend: segment grouping**: Map page defaults to "Group by Segment" mode, dropdown to switch to subnet mode
- [x] **Frontend: gateway hub rendering**: Gateway nodes render as large orange diamonds with bold labels; legend updated
- [x] **Frontend: node info panel**: Shows gateway badge and segment name when available

### Phase 3 — Cross-Segment Visibility + Traceroute ✅

- [x] **Cross-segment edge styling**: Edges between different segments now render as amber dashed lines (width 2, `[8,4]` dash, curvedCCW smooth). Regular intra-segment edges remain solid gray.
- [x] **Segment filter dropdown**: Map page shows segment filter when in segment mode — populated from backend `segments` data. Clears subnet filter on mode switch and vice versa.
- [x] **Backend `segment_filter` param**: `/api/network/map` accepts `segment_filter` to show only hosts in a specific segment.
- [x] **Traceroute path overlay**: Route edges merged into map when "Show Routes" is enabled. Green dashed lines with directional arrows, distinct from both regular and cross-segment edges.
- [x] **Enhanced legend**: Shows edge types (regular, cross-segment, route path) with visual indicators.
- [x] **Stats bar**: Shows cross-segment edge count in segment mode; shows route path count when routes enabled.

### Bug Fixes ✅

- [x] **Netstat import 500 error**: Fixed `NOT NULL constraint failed: connections.remote_port` for LISTEN state connections. Made column nullable, added SQLite table migration, wrapped bulk DB ops in savepoints to prevent `PendingRollbackError`.
- [x] **Vendor lookup returning 0**: `mac-vendor-lookup` package uses `asyncio.run_until_complete()` internally which crashes inside uvicorn's event loop. Rewrote to read the vendor file directly (38,437 OUI entries loaded at import time).
- [x] **Pydantic `ConnectionResponse` schema**: Made `remote_port` `Optional[int]` to match the nullable DB column.
- [x] **Vendor lookup "undefined" in UI**: Fixed field name mismatch (`vendors_updated` vs `updated`) between backend response and frontend.

## Remaining Work

- [ ] Re-import nmap data with `-O -A` flags to get hostname/OS enrichment
- [ ] WebSocket support for real-time map updates

## Architecture Failure Modes Review (2026-02-09)

Top reliability/security risks identified from current architecture and code paths:

- [ ] **SQLite write contention / latency collapse**: Inline import, correlation, cleanup, and map generation all hit one SQLite writer path. Trigger: concurrent ingest + map queries.
- [ ] **Data-loss risk in maintenance flows**: Cleanup permanently deletes records; backup/restore uses file copies of the active SQLite DB. Trigger: restore/cleanup during active traffic or without validated recovery drills.
- [ ] **Identity consistency drift**: Host correlation can over-merge when tag confidence is insufficient. Trigger: sparse or conflicting source data with overlapping hostnames/FQDNs.
- [ ] **Auth misconfiguration exposure**: `AUTH_ENABLED=True` + `ENFORCE_AUTH=False` permits anonymous synthetic admin behavior. Trigger: production deployment without `ENFORCE_AUTH=True`.
- [ ] **External dependency outages**: OIDC and GitHub update checks rely on outbound HTTP calls. Trigger: provider/API timeout or outage.

Planned mitigation themes:

- [ ] Move heavy ingest/correlation work off request path (or chunk and isolate transactions).
- [ ] Add backup integrity checks and restore rehearsals; document operational guardrails for cleanup/restore.
- [ ] Tighten merge heuristics and add post-correlation anomaly checks.
- [ ] Add startup/runtime config guardrails for auth and JWT secret hardening.
- [ ] Add degraded-mode handling/alerts for OIDC and update-check dependency failures.

## Review

**Phase 1 root cause**: The ARP parser's `detect_format()` had a priority bug — lines starting with `?` (unresolved hostnames in Linux `arp -a`) were matched by the macOS check first. The macOS parser's `(.+?)` regex then captured `[ether]` as part of the MAC address. Fixed by checking for `[ether]` vs `[ethernet]`/`ifscope` markers to disambiguate platforms.

**Phase 2 approach**: Segment grouping derives from ARP interface names at query time — no new DB model needed. This is lightweight and accurate since the ARP table already maps IPs to physical/virtual network interfaces. Gateway detection uses the existing `device_type` field set by the migration script.

**Phase 3 approach**: Cross-segment edges are detected by comparing the ARP-derived segment of each endpoint. Edge styling is set in the backend (dashes, color, width) so vis-network renders them directly. Traceroute paths are converted from IP-based `path_edges` to host-ID-based edges in the frontend, with distinct green dashed styling and directional arrows.

**Vendor lookup fix**: The `mac-vendor-lookup` package's sync API calls `asyncio.get_event_loop().run_until_complete()` which fails inside uvicorn's already-running event loop with "this event loop is already running." Fixed by reading the package's downloaded vendor file (`mac-vendors.txt`) directly at import time, building a plain dict for O(1) lookups.

**Data gap**: The nmap XML only contained service/port data for a single host (10.180.0.20) with no OS detection or hostname resolution. Users need to re-scan with `nmap -O -A` to get enriched host data.

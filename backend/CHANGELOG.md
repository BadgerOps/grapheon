# Changelog

All notable changes to the Grapheon backend will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## 0.8.2 - 2026-02-08
### Fixed
- **OAuth2 provider configuration**: added `authorization_endpoint`, `token_endpoint`, and `userinfo_endpoint` fields to provider create/update schemas so non-OIDC OAuth2 providers (e.g. GitHub) can be fully configured without relying on OIDC discovery
- **OIDC discovery guard**: discover endpoint now returns a clear 400 error for `oauth2`-type providers instead of attempting `.well-known/openid-configuration` lookup (which always 404s for pure OAuth2 providers)
- **GitHub token exchange**: `exchange_code()` now sends `Accept: application/json` header and handles form-encoded responses (GitHub returns `application/x-www-form-urlencoded` by default)
- **OAuth2 userinfo normalisation**: `fetch_userinfo()` maps non-standard claim names to OIDC equivalents (`id` → `sub`, `login` → `preferred_username`) so downstream identity extraction works for GitHub and similar OAuth2 providers
- **GitHub private email fallback**: when GitHub's `/user` endpoint returns `email: null` (user has private email), the service fetches the primary verified email from `/user/emails`

## 0.8.1 - 2026-02-07
### Added
- **In-app Identity & Access admin page** with three tabs: Providers, Role Mappings, and Users
- Admin CRUD endpoints for auth provider management: `GET/POST /api/auth/admin/providers`, `PATCH/DELETE /api/auth/admin/providers/{id}`, `POST /api/auth/admin/providers/{id}/discover`
- Admin CRUD endpoints for role mapping management: `GET/POST /api/auth/admin/providers/{id}/mappings`, `PATCH/DELETE /api/auth/admin/mappings/{id}`
- User active status toggle endpoint: `PATCH /api/auth/users/{id}/active`
- OIDC discovery trigger endpoint caches `authorization_endpoint`, `token_endpoint`, and `userinfo_endpoint` on demand
- 13 new admin CRUD tests covering provider CRUD, mapping CRUD, user active toggle, and authorization enforcement

### Fixed
- Login page now redirects to dashboard after successful local or OIDC login (was staying on login page)

## 0.8.0 - 2026-02-07
### Added
- **Multi-provider OIDC authentication** with support for Okta, Google, GitHub, GitLab, Authentik, and any standards-compliant OIDC provider
- **3-tier RBAC** (admin/editor/viewer) enforced on all 53 API endpoints via FastAPI dependencies
- **Local admin fallback** for bootstrap/break-glass scenarios with bcrypt password hashing
- New `auth` package: `jwt_service.py` (HS256 JWT creation/validation), `oidc_service.py` (OIDC discovery, code exchange, userinfo, role mapping), `dependencies.py` (FastAPI auth dependencies), `abac_stubs.py` (future ABAC placeholder)
- New models: `User`, `AuthProvider`, `RoleMapping` with full SQLAlchemy async support
- Auth API endpoints: `GET /api/auth/providers`, `POST /api/auth/callback`, `POST /api/auth/login/local`, `GET /api/auth/me`, `POST /api/auth/logout`, `GET /api/auth/users` (admin), `PATCH /api/auth/users/{id}/role` (admin)
- Feature flags: `AUTH_ENABLED` (master switch) and `ENFORCE_AUTH` (gradual rollout) for backward-compatible deployment
- Automatic local admin bootstrap from `LOCAL_ADMIN_USERNAME/EMAIL/PASSWORD` environment variables on first startup
- IdP-to-app role mapping via `RoleMapping` table with support for dotted claim paths (e.g., `resource_access.app.roles`)
- Audit logger now tracks authenticated actor via ContextVar (replaces hardcoded "user" strings)
- 33 new auth tests covering JWT, endpoints, RBAC, role mapping, OIDC service, feature flags, local admin bootstrap, and provider registration
- Added `authlib`, `bcrypt`, `python-jose[cryptography]` to dependencies

## 0.7.0 - 2026-02-07
### Added
- Network topology export in **GraphML** format (`GET /api/export/network/graphml`): standard XML graph format importable by Gephi, yEd, Cytoscape Desktop, and other graph analysis tools
- Network topology export in **draw.io** format (`GET /api/export/network/drawio`): produces `.drawio` XML files openable in draw.io (desktop or web) with collapsible VLAN/subnet containers, device-type styling, and auto-positioned nodes
- New `export_converters` package with `graphml_exporter` and `drawio_exporter` modules
- `_fetch_network_elements()` helper in the export router that reuses the full `/api/network/map` pipeline (node building, edge building, gateway resolution) for export endpoints
- Both endpoints accept `subnet_filter` and `show_internet` query parameters matching the map API
- 28 new unit tests covering both converter modules (XML structure, hierarchy, data attributes, special characters, empty inputs) and API endpoints (status codes, content types, content-disposition headers)
- Added `networkx>=3.2` and `drawpyo>=0.2.5` to `requirements.txt`

## 0.6.0 - 2026-02-06
### Changed
- Refactored `routers/network.py` (1060+ lines) into `backend/network/` package with 7 extracted modules: constants, validators, styles, queries, nodes, edges, legacy_format
- Network router is now a slim orchestrator (~325 lines) that delegates to the extracted modules
- Fixed N+1 port count query: replaced per-host `SELECT COUNT(*)` loop with a single `GROUP BY` batch query in both `/api/network/map` and `/api/network/subnets` endpoints
- Fixed shared gateway edge bug: gateway-to-subnet edges are now properly separated from node data during node building

### Added
- Upgrade watcher script (`scripts/grapheon-upgrade.sh`): reads `/data/upgrade-requested`, pulls container images, restarts systemd services, runs health check, writes status to `/data/upgrade-status.json`
- Systemd path unit (`deploy/grapheon-upgrade.path`): watches for upgrade marker file
- Systemd service unit (`deploy/grapheon-upgrade.service`): executes upgrade script
- Updated deployment docs with in-app upgrade installation and rollback instructions

## 0.5.0 - 2026-02-06
### Added
- `DeviceIdentity` model for non-destructive linking of multi-homed network devices (routers/switches with interfaces on multiple VLANs/subnets)
- Full CRUD REST API at `/api/device-identities` with host link/unlink endpoints
- `device_id` column on hosts table (nullable FK to device_identities) with auto-migration
- Correlation engine Phase 2 now creates DeviceIdentity records from shared MAC addresses instead of destructively merging multi-homed hosts
- `create_device_identity_from_mac()` function with device type inference from hostname patterns
- Network map shared gateway combining: DeviceIdentity-linked gateways render as a single node spanning multiple subnets
- Network map public IP grouping: `show_internet=show` groups public IPs under a "Public IPs" compound node
- `is_private_ip()` utility covering RFC1918, loopback, link-local, CGNAT, and IPv6 ULA ranges
- Seed data updated with shared MAC gateways across VLANs 20/30/40 for multi-homed router demonstration

### Fixed
- Network map edge integrity: `ip_to_host_id` no longer populated for skipped hosts (public IPs in cloud/hide mode, shared gateway hosts), preventing Cytoscape "nonexistent target" errors

## 0.4.1 - 2026-02-06
### Fixed
- "Check for Updates" button now bypasses the 1-hour server-side release cache so manual checks always fetch fresh data from GitHub instead of returning stale cached results
- Added `force` query parameter to `GET /api/updates` endpoint; when `true`, skips the in-memory release cache and queries the GitHub Releases API directly

## 0.4.0 - 2026-02-06
### Added
- Backup upload endpoint (`POST /api/maintenance/backup/upload`): accepts `.db` file uploads from the browser, saves to the server's backup directory, and makes them available for restore
  - File extension validation (`.db` only) with clear error messaging
  - Path traversal protection via `os.path.basename()` sanitization
  - Automatic timestamp-suffixed renaming when a file with the same name already exists
- Demo data seed endpoint (`POST /api/maintenance/seed-demo`): triggers the built-in `seed_demo_data.py` script from the API without requiring CLI access
  - `append` query parameter: when `true`, adds demo data alongside existing records; when `false` (default), clears all data first
  - Runs as a subprocess with 60-second timeout and full stdout/stderr capture
  - Returns script output to the frontend for inline display

### Changed
- Added `UploadFile` and `File` imports from FastAPI for multipart file handling in the maintenance router

## 0.3.0 - 2026-02-05
### Added
- In-app update check: new `/api/updates` endpoint queries GitHub Releases API for latest versions (1-hour cached)
- In-app upgrade trigger: `POST /api/updates/upgrade` writes a trigger file for the host-level systemd path unit
- Upgrade status polling: `GET /api/updates/status` reads progress from the host upgrade handler
- New `updates` router with full semver comparison for backend and frontend versions
- Added `httpx` dependency for async HTTP requests to GitHub API

## 0.2.0 - 2026-02-05
### Added
- VLAN support: new `VLANConfig` model with subnet-to-VLAN CIDR mapping
- VLAN CRUD API (`/api/vlans`) with auto-assign endpoint that matches hosts to VLANs by IP/subnet
- `vlan_id` and `vlan_name` columns on Host model with database migration
- Cytoscape.js network map API (`/api/network/map`) returning compound node hierarchy (VLAN -> Subnet -> Host)
- Internet/public IP routing: RFC1918 private IP detection, gateway auto-detection, Internet cloud node consolidation
- `show_internet` parameter: 'cloud' (route through gateway), 'hide' (exclude), 'show' (raw)
- `route_through_gateway` parameter: rewrites cross-subnet/cross-VLAN edges as host->gateway->gateway->host chains
- Demo seed data script (`scripts/seed_demo_data.py`) with 6 VLANs, 48 hosts, ports, connections, ARP, and traceroute data
- Seed script supports `--export` and `--restore` for JSON backup/restore

### Changed
- Network map endpoint (`/api/network/map`) completely rewritten for Cytoscape.js elements format
- Edge classification: same_subnet, cross_subnet, cross_vlan, to_gateway, internet connection types
- Device type styling with distinct shapes/colors for router, switch, firewall, server, workstation, printer, IoT
- Legacy vis-network format preserved via `format=legacy` parameter for backward compatibility

## 0.1.2 - 2026-02-04
### Added
- MAC vendor lookup service (`services/mac_vendor.py`) with built-in OUI database (~400 common vendors)
- Vendor lookup endpoints:
  - `POST /api/maintenance/vendor-lookup` - Update vendor info for all hosts
  - `GET /api/maintenance/vendor-lookup/{mac}` - Single MAC address lookup
- Database backup/restore endpoints:
  - `POST /api/maintenance/backup` - Create database backup
  - `GET /api/maintenance/backup/list` - List available backups
  - `GET /api/maintenance/backup/download/{filename}` - Download a backup file
  - `POST /api/maintenance/restore/{filename}` - Restore database from backup
  - `DELETE /api/maintenance/backup/{filename}` - Delete a backup file

### Fixed
- Nmap parser now extracts `device_type` from `<osclass type="...">` element
- Added `_normalize_device_type()` method to map nmap device types to standard categories (server, workstation, router, switch, firewall, printer, phone, IoT, storage, virtual, unknown)

### Changed
- Maintenance router expanded with comprehensive backup and vendor management capabilities

## 0.1.0 - 2026-02-03
### Added
- Initial FastAPI backend with ingestion parsers, correlation, and search APIs.

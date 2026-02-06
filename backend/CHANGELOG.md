# Changelog

All notable changes to the Grapheon backend will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

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

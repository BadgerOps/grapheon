# Changelog

All notable changes to the Grapheon backend will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

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

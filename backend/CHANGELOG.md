# Changelog

All notable changes to the Grapheon backend will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

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

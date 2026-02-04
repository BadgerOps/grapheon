# Changelog

All notable changes to the Grapheon frontend will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## 0.1.2 - 2026-02-04
### Added
- New Settings/Config page (`/config`) for system maintenance and configuration
- Database backup management UI: create, download, restore, and delete backups
- MAC vendor lookup trigger to update vendor information for all hosts
- Data cleanup UI with configurable retention period and preview
- Database statistics display showing hosts, ports, connections, and database size
- New Vendor column in HostTable showing manufacturer information
- Color-coded badges for OS family and device type in HostTable
- New API client methods for maintenance endpoints (vendor lookup, backup/restore)

### Fixed
- Dark mode styling on Hosts page - all elements now properly themed
- HostTable dark mode support with proper contrast and borders
- NetworkMap theme change detection using MutationObserver (fixed initialization order)

### Changed
- Settings navigation link added to main navbar with gear icon

## 0.1.1 - 2026-02-04
### Added
- Working light/dark mode toggle button with localStorage persistence
- Theme flash prevention script in index.html
- NetworkMap component now responds to theme changes dynamically

### Fixed
- Navbar and footer now properly use light colors in light mode
- NavLink component properly styled for both light and dark modes
- Network canvas background now has explicit light mode color

### Changed
- Theme indicator converted from display-only to clickable toggle button
- Footer now displays current version number from package.json

## 0.1.0 - 2026-02-03
### Added
- Initial React/Vite interface for network aggregation workflows.

# Changelog

All notable changes to the Grapheon frontend will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## 0.3.0 - 2026-02-05
### Added
- In-app update notification banner: polls backend for available updates every 60 minutes
- UpdateBanner component with expandable release notes, upgrade confirmation dialog, and progress tracking
- Dismissible banner with localStorage persistence (reappears for new versions)
- Upgrade flow: confirm → in-progress (with status polling) → complete (auto-refresh) or error (retry)
- New API client methods: `checkForUpdates()`, `triggerUpgrade()`, `getUpgradeStatus()`
- Slide-down animation for banner appearance
- Manual "Check for Updates" button in Settings page with version info and current version badges
- Update modal in Settings: shows version comparison, release notes, release date, GitHub link, and upgrade option

## 0.2.0 - 2026-02-05
### Added
- Cytoscape.js network visualization replacing vis-network, with compound node hierarchy (VLAN -> Subnet -> Host)
- Three layout modes: hierarchical (dagre), grouped (fcose), force-directed (cola)
- CytoscapeNetworkMap component with zoom/pan controls, stats overlay, interactive legend, and selected node info panel
- Full light/dark mode Cytoscape stylesheets with device-type-specific shapes and colors
- Client-side graph filtering: filter by VLAN, device type, or subnet without API re-fetches
- Search-and-focus: find devices by IP or hostname with animated zoom
- Internet mode selector: collapse public IPs into cloud node, hide, or show raw
- "Route via GW" toggle: visualize cross-subnet traffic routing through gateway nodes
- VLAN filter dropdown and device type filter bar with toggle chips
- VLAN management API client methods (CRUD + auto-assign)
- Edge legend showing same-subnet, cross-subnet, cross-VLAN, internet, and route path styles

### Changed
- Map page completely rewritten with new controls toolbar and stats bar
- Network visualization now uses compound nodes for VLAN/subnet grouping instead of flat force-directed graph
- Internet node filtering: stays visible when connected gateways pass filters, dims when all connections are filtered

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

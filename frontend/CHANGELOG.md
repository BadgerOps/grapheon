# Changelog

All notable changes to the Grapheon frontend will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## 0.8.0 - 2026-02-07
### Added
- **Login page** with OIDC provider buttons (PKCE flow) and local admin credential form
- **AuthContext** provider with JWT token management, automatic validation on mount, role-based access helpers
- **ProtectedRoute** component wrapping all app routes with auth check and role-based access control
- **UserMenu** dropdown in navigation showing username, role badge, and sign-out button
- Bearer token automatically attached to all API requests via `api/client.js`
- 401 response handling: automatic token clearance and redirect to login
- Role-based nav link visibility (Import hidden for viewers, Settings hidden for non-admins)
- New auth API client functions: `getProviders()`, `authCallback()`, `localLogin()`, `getCurrentUser()`, `authLogout()`, `getUsers()`, `updateUserRole()`

## 0.7.0 - 2026-02-07
### Added
- **Export dropdown** on the network map replacing the single PNG button: hover menu offers PNG image, SVG vector, GraphML (for Gephi/yEd), and draw.io (for diagrams.net) exports
- `exportNetworkGraph()` helper in `mapExport.js` that fetches graph exports from the backend API and triggers browser file download
- `exportNetworkGraphML()` and `exportNetworkDrawio()` API client methods

### Changed
- Changelog page completely rewritten: replaces raw `react-markdown` rendering with a structured, interactive timeline UI featuring version badges, category icons (Added/Changed/Fixed), collapsible release cards, search filtering, combined "All Changes" view interleaving frontend and backend releases, and summary stats bar
- Removed `react-markdown` and `remark-gfm` dependencies (no longer used anywhere in the codebase)

## 0.6.0 - 2026-02-06
### Fixed
- Legend shape mismatches: Switch now shows vee (was triangle), Server shows round-rectangle (was square), Printer shows rectangle (was square) to match actual Cytoscape node shapes
- Edge legend colors now update when switching between light and dark mode (`getEdgeLegend(isDark)` replaces static color values)
- Dark mode default node color changed from #6b7280 to #9ca3af for better visibility against dark backgrounds
- Dark mode default node border color changed from #9ca3af to #d1d5db for improved contrast
- `selectedNode` state now clears automatically when map elements change, preventing stale node info panel
- Added null checks for `containerRef.current` in zoom handlers before accessing `clientWidth`/`clientHeight`
- Added try/catch around `cytoscape()` constructor in `initCytoscape()` to prevent full page crash on initialization errors
- Added try/catch around fullscreen resize callback
- Added null check and warning log in `runLayout()` for invalid layout mode names

### Added
- `MapErrorBoundary` component: catches Cytoscape rendering errors and shows a fallback UI with retry button instead of crashing the page
- Inline warning banners in Map page when VLAN, subnet, or route data fails to load (previously only logged to console)
- Map page no longer renders CytoscapeNetworkMap below a primary error message
- Shared gateway and gateway border indicators in device legend

## 0.5.0 - 2026-02-06
### Added
- Map fullscreen toggle using browser Fullscreen API
- Map pop-out window at `/map/fullscreen` for chromeless visualization
- PNG and SVG export buttons using Cytoscape built-in `cy.png()` / `cy.svg()`
- `mapExport.js` service module for export and fullscreen utilities
- `MapFullscreen.jsx` page component for dedicated full-viewport map view
- Cytoscape theme selectors for "Public IPs" compound node, shared gateway nodes, and public IP host nodes (light + dark mode)
- Edge and device legend entries for `to_gateway` and `internet` connection types
- Device identity API client methods: CRUD, link/unlink hosts to devices

### Changed
- `App.jsx` conditionally hides nav/footer when on fullscreen map route
- `CytoscapeNetworkMap.jsx` gains fullscreen state management, three new control buttons, and updated legend

## 0.4.1 - 2026-02-06
### Fixed
- "Check for Updates" button in Settings now bypasses the server-side release cache, so manual checks always query GitHub for the latest version instead of returning stale cached results
- `checkForUpdates()` API client now accepts an optional `force` parameter; the Settings button passes `force=true` while the auto-poll UpdateBanner continues using the cached path to avoid GitHub rate-limiting

## 0.4.0 - 2026-02-06
### Added
- **Import Backup** button in Settings > Database Backup & Restore section
  - Opens a native file picker filtered to `.db` files
  - Uploads the selected backup to the server via multipart POST
  - Uploaded backups immediately appear in the backup list and can be restored, downloaded, or deleted
  - Client-side file extension validation before upload
  - Loading spinner and success/error feedback with auto-dismiss
  - File input automatically resets after upload so the same file can be re-selected
- **Test Data Generation** section in Settings page (between Backup and Cleanup)
  - "Generate Fresh Data" button: clears all existing data and seeds a full demo network (6 VLANs, ~48 hosts, ports, connections, ARP entries, traceroute hops)
  - "Append to Existing" button: adds demo data alongside current records without clearing
  - Both actions show a confirmation dialog explaining the destructive/additive behavior
  - Script output displayed inline in a scrollable panel after generation completes
  - Database statistics automatically refresh after seeding
- New API client functions: `uploadBackup(file)` and `seedDemoData(append)`

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

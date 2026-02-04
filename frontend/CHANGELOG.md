# Changelog

All notable changes to the Grapheon frontend will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

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

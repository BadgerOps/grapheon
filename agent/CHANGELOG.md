# Changelog

All notable changes to the Graphēon passive agent will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## 0.2.0 - 2026-03-22
### Added
- **Deployable passive runtime**: first host-side Graphēon passive agent release with outbound-only registration and check-in, local passive collection, gzip-compressed delta reports, and low-impact policy-driven cadence
- **Manual CLI mode**: direct flag-driven execution with `--register-only`, `--check-in-only`, `--force`, and built-in `--help` examples for manual rollout and debugging
- **Systemd deployment bundle**: shipped `grapheon-agent.service`, `grapheon-agent.timer`, example env file, and install helper for one-shot scheduled execution
- **Release packaging**: new versioned GitHub release tarball and GHCR container image for agent distribution

### Changed
- Agent runtime now reads its own version from `agent/VERSION` instead of using a hardcoded string

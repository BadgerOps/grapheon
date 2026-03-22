# Changelog

All notable changes to the Graphēon passive agent will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## 0.3.0 - 2026-03-22
### Added
- **Versioned install layout**: host installs now land under `/opt/grapheon/agent/releases/<version>/` with `/opt/grapheon/agent/current` as the active symlink target
- **Lifecycle helper scripts**: added `upgrade-passive-agent.sh`, `rollback-passive-agent.sh`, and `uninstall-passive-agent.sh` for release-based host management
- **Rollback test coverage**: packaging tests now verify versioned installs and rollback of the active `current` symlink using a fake `systemctl`
- **Artifact verification metadata**: the release workflow now uploads `grapheon-agent-vX.Y.Z.tar.gz.sha256` alongside the tarball

### Changed
- `install-passive-agent.sh` now installs a versioned release directory and updates the stable `current` symlink instead of overwriting a single in-place runtime path
- The shipped systemd service now executes `/opt/grapheon/agent/current/grapheon_agent.py` so upgrades and rollbacks do not require editing the unit file
- Agent packaging docs now cover release verification, upgrade, rollback, uninstall, and the versioned install layout

## 0.2.0 - 2026-03-22
### Added
- **Deployable passive runtime**: first host-side Graphēon passive agent release with outbound-only registration and check-in, local passive collection, gzip-compressed delta reports, and low-impact policy-driven cadence
- **Manual CLI mode**: direct flag-driven execution with `--register-only`, `--check-in-only`, `--force`, and built-in `--help` examples for manual rollout and debugging
- **Systemd deployment bundle**: shipped `grapheon-agent.service`, `grapheon-agent.timer`, example env file, and install helper for one-shot scheduled execution
- **Release packaging**: new versioned GitHub release tarball and GHCR container image for agent distribution

### Changed
- Agent runtime now reads its own version from `agent/VERSION` instead of using a hardcoded string

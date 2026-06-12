# Changelog

All notable changes to the Graphēon passive agent will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## 0.16.0 - 2026-06-11
### Added
- **Richer passive capture parsing**: tcpdump evidence now preserves VLAN IDs, extended LLDP/CDP details, DHCPv4/DHCPv6 options, IPv6 RA prefixes/DNS/MTU hints, DNS PTR/CNAME/SRV/SVCB/HTTPS records, NBNS names, SSDP and WS-Discovery labels, STP/LACP neighbor hints, HSRP/VRRP/CARP gateway hints, OSPF/RIP/EIGRP/BGP map hints, and aggregated optional flow counters.

### Fixed
- **Schema-safe passive service names**: DNS, mDNS, and NBNS names with display characters such as spaces are normalized before check-in so backend validation does not reject the run; the original value is preserved in evidence metadata as `raw_name`.

## 0.15.0 - 2026-06-11
### Added
- **Passive topology evidence config**: the stdlib agent now exposes config knobs for bounded normalized topology evidence file ingest, interface ignore filters, and passive tcpdump observation windows.
- **Topology evidence payloads**: check-ins now include a `topology_evidence` section when configured JSON collector output is available.
- **Topology evidence tests**: added agent coverage for bounded topology evidence file loading and configured collector output forwarding.
- **Bounded passive capture**: configured or admin-requested collection can run a short local tcpdump window, parse LLDP/CDP, ARP, DHCP, DNS-family, IPv6 ND/RA, and optional header-only flow summaries into topology evidence, then delete the temporary pcap without uploading it.

### Fixed
- **Immediate requested passive collection**: admin-requested agent collections now bypass policy jitter as well as cached cadence so requested passive refreshes start immediately.
- **Passive capture default interface**: capture requests without explicit interfaces now use default-route interfaces instead of tcpdump's `any` pseudo-device, which cannot compile Ethernet-header LLDP/CDP filters.

## 0.14.0 - 2026-06-11
### Added
- **Local network noise filtering**: `GRAPHEON_AGENT_IGNORE_LOCAL_NET=true` / `--ignore-local-net` drops loopback, link-local, unspecified, reserved/multicast IPs, and common local virtualization bridge interfaces from agent collection.
- **Startup version logging**: each agent invocation logs the passive agent version before registration, polling, or collection decisions.

### Changed
- **Fast control-plane polling**: the shipped systemd timer and default local timer interval now run every 15 seconds so UI-requested agent collections are picked up promptly while backend policy still gates full passive collection frequency.
- **Precise timer cadence**: the shipped systemd timer now sets `AccuracySec=1s` so the 15-second control-plane poll is not delayed by systemd's default one-minute timer coalescing window.

## 0.13.1 - 2026-06-11
### Fixed
- **Systemd restart responsiveness**: the shipped agent service now uses `Type=simple` with `RuntimeMaxSec=10min` so `systemctl restart grapheon-agent.service` returns after the supervised agent process starts instead of blocking through policy jitter and collection.
- **Local API-key recovery**: if a stored API key is rejected during agent control polling and an enrollment key is configured, the agent clears the stale local key and attempts enrollment registration to recover from backend database resets or lost server-side key state.

## 0.13.0 - 2026-06-11
### Added
- **On-demand collection polling**: the passive agent now polls Graphēon for pending collection requests on each timer run and bypasses local cadence when an admin-requested collection is pending.

## 0.12.1 - 2026-06-11
### Fixed
- **Edge registration compatibility**: the passive agent now sends a deterministic `User-Agent` header on JSON requests and supports `GRAPHEON_AGENT_USER_AGENT` / `--user-agent` overrides for stricter edge policies.
- **Systemd oneshot timeout**: the shipped service now uses `TimeoutStartSec=10min` instead of ignored `RuntimeMaxSec=10min` for the oneshot collector.
- **Agent registration troubleshooting docs**: documented Cloudflare/WAF-style `403` / `error code: 1010` registration failures, the `/api/agents/*` edge bypass recommendation, normal first-run API-key bootstrap logs, and installed host `current/` paths.

## 0.12.0 - 2026-06-11
### Changed
- **Full-snapshot check-ins**: the passive agent now sends full passive snapshots on each check-in so the backend can mark missing agent-scoped observations stale/removed.
- **Backend-aligned versioning**: the passive agent version is aligned with the backend API version for compatibility reporting.

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

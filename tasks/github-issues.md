# GitHub Issues to Create

## Issue 1: Auth config guardrails for production deployments
**Labels**: security, enhancement

### Description
`AUTH_ENABLED=True` + `ENFORCE_AUTH=False` silently permits anonymous synthetic admin access in production. This is a dangerous misconfiguration that should be caught early.

### Acceptance Criteria
- [ ] Startup warning when `AUTH_ENABLED=True` but `ENFORCE_AUTH=False`
- [ ] Log loud warnings when `JWT_SECRET` is the default/weak value
- [ ] Consider hard failure in production mode for unsafe auth configs
- [ ] Document required production auth settings

---

## Issue 2: Backup integrity checks and restore validation
**Labels**: reliability, enhancement

### Description
Maintenance cleanup permanently deletes records. Backup/restore uses file copies with no validation. A restore during active traffic without validated recovery drills risks data loss.

### Acceptance Criteria
- [ ] Add backup integrity checks (checksum validation)
- [ ] Add restore rehearsal/dry-run capability
- [ ] Document backup and restore procedures
- [ ] Add safety confirmation for destructive cleanup operations

---

## Issue 3: Host correlation confidence and over-merge prevention
**Labels**: bug, data-integrity

### Description
Host correlation can over-merge when tag confidence is insufficient. Sparse or conflicting source data with overlapping hostnames/FQDNs can trigger incorrect merges.

### Acceptance Criteria
- [ ] Tighten merge heuristics with confidence scoring
- [ ] Add post-correlation anomaly checks
- [ ] Provide merge undo/split capability for incorrectly merged hosts
- [ ] Log merge decisions with confidence scores for auditability

---

## Issue 4: ABAC implementation using Casbin
**Labels**: security, feature

### Description
Three ABAC stubs in `backend/auth/abac_stubs.py` currently return `True` unconditionally (`can_access()`, `can_access_subnet()`, `can_export()`). Implement fine-grained attribute-based access control.

### Acceptance Criteria
- [ ] Integrate Casbin (pycasbin) with SQLAlchemy adapter
- [ ] Implement subnet-level access control via `user.user_metadata["allowed_subnets"]`
- [ ] Implement export restrictions based on user attributes
- [ ] Admin UI for managing ABAC policies

---

## Issue 5: WebSocket support for real-time topology updates
**Labels**: feature, enhancement

### Description
Currently the map view requires manual refresh or polling to see topology changes. WebSocket support would enable live updates when new scans are imported or hosts are correlated.

### Acceptance Criteria
- [ ] WebSocket endpoint for topology change notifications
- [ ] Frontend auto-reconnect with backoff
- [ ] Incremental graph updates (add/remove/modify nodes/edges) without full reload
- [ ] Connection status indicator in UI

---

## Issue 6: File validation hardening (ClamAV, magic bytes, strict mode)
**Labels**: security, enhancement

### Description
Current file validation in `backend/services/file_validator.py` logs warnings but does NOT reject files. Needs virus scanning, file header validation, and a strict mode option.

### Acceptance Criteria
- [ ] ClamAV integration via clamd socket for virus scanning
- [ ] Magic byte validation to ensure file content matches declared source_type
- [ ] Strict mode config option that rejects files with validation errors
- [ ] Rejection logging and user-facing error messages

---

## Issue 7: Re-import nmap data with OS/service enrichment
**Labels**: data-quality, enhancement

### Description
Current nmap XML data was imported from a minimal scan lacking hostname and OS enrichment. Re-scanning with `-O -A` flags would provide OS detection, service versions, and script output.

### Acceptance Criteria
- [ ] Document recommended nmap scan flags for maximum enrichment
- [ ] Handle re-import gracefully (merge with existing host data, don't duplicate)
- [ ] Parse and display OS detection results in host detail view
- [ ] Parse service version info from `-sV` output

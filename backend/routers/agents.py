import gzip
import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
from ipaddress import ip_address as parse_ip
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_admin
from config import settings
from database import get_db
from models import (
    ARPEntry,
    Agent,
    AgentCheckIn,
    AgentEnrollmentKey,
    AgentObservation,
    AgentPolicy,
    Connection,
    EntityEvidence,
    Host,
    RawImport,
    User,
)
from schemas import (
    AgentApprovalRequest,
    AgentApiKeyRotateRequest,
    AgentApiKeyRotateResponse,
    AgentCheckInRecordResponse,
    AgentCheckInRequest,
    AgentCheckInResponse,
    AgentCollectionRequestCreate,
    AgentCollectionRequestStatus,
    AgentCompatibilityResponse,
    AgentCreate,
    AgentEnrollmentKeyCreate,
    AgentEnrollmentKeyCreateResponse,
    AgentEnrollmentKeyResponse,
    AgentEnrollmentKeyUpdate,
    AgentHealthResponse,
    AgentObservationResponse,
    AgentPolicyCreate,
    AgentPolicyResponse,
    AgentPolicyUpdate,
    AgentPollRequest,
    AgentPollResponse,
    AgentRegistrationRequest,
    AgentRegistrationResponse,
    AgentReactivateRequest,
    AgentRejectRequest,
    AgentRevokeRequest,
    AgentResponse,
    AgentUpdate,
    PaginatedResponse,
)
from utils.audit import audit
from utils.tagging import (
    build_arp_tags,
    build_connection_tags,
    build_host_tags,
    merge_tags,
)
from services.mac_vendor import lookup_mac_vendor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])

AGENT_SOURCE_TYPE = "agent"
AGENT_IMPORT_TYPE = "agent"
AGENT_SOURCE_ORIGIN = "agent"
ENROLLMENT_KEY_PREFIX = "gaek"
AGENT_API_KEY_PREFIX = "gpak"
MIN_SUPPORTED_AGENT_VERSION = "0.1.0"

AGENT_SECTION_POLICY = {
    "addresses": ("ip_addr", "address"),
    "neighbors": ("ip_neigh", "neighbor"),
    "connections": ("ss_tunap", "connection"),
    "routes": ("ip_route", "route"),
    "topology_evidence": ("topology_evidence", "topology_evidence"),
}

DEFAULT_HEALTH_INTERVAL_SECONDS = 3600
DEFAULT_HEALTH_JITTER_SECONDS = 300


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash_secret(raw_secret: str) -> str:
    return hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()


def _generate_secret(prefix: str) -> tuple[str, str]:
    token = f"{prefix}_{secrets.token_urlsafe(32)}"
    return token, token[:20]


def _issue_agent_api_key(agent: Agent, issued_at: datetime) -> str:
    raw_api_key, api_key_prefix = _generate_secret(AGENT_API_KEY_PREFIX)
    agent.api_key_hash = _hash_secret(raw_api_key)
    agent.api_key_prefix = api_key_prefix
    agent.api_key_issued_at = issued_at
    return raw_api_key


def _clear_agent_api_key(agent: Agent) -> None:
    agent.api_key_hash = None
    agent.api_key_prefix = None
    agent.api_key_issued_at = None


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _semver_tuple(value: Optional[str]) -> Optional[tuple[int, int, int]]:
    if not value:
        return None
    raw = value.strip()
    if raw.startswith("v"):
        raw = raw[1:]
    core = raw.split("-", 1)[0].split("+", 1)[0]
    parts = core.split(".")
    if len(parts) != 3:
        return None
    try:
        return tuple(int(part) for part in parts)
    except ValueError:
        return None


def _agent_compatibility(reported_version: Optional[str]) -> AgentCompatibilityResponse:
    backend_version = settings.APP_VERSION
    backend_semver = _semver_tuple(backend_version)
    minimum_semver = _semver_tuple(MIN_SUPPORTED_AGENT_VERSION)
    reported_semver = _semver_tuple(reported_version)

    status_value = "unsupported"
    warning = None
    if reported_semver is None:
        warning = (
            "Agent version was not reported or is not semantic; accepting with "
            "limited compatibility guarantees"
        )
    elif minimum_semver and reported_semver < minimum_semver:
        warning = (
            f"Agent version {reported_version} is older than the minimum "
            f"supported version {MIN_SUPPORTED_AGENT_VERSION}; accepting with warning"
        )
    elif backend_semver and reported_semver > backend_semver:
        status_value = "newer_untested"
        warning = (
            f"Agent version {reported_version} is newer than backend "
            f"{backend_version}; accepting as untested"
        )
    elif backend_semver and reported_semver < backend_semver:
        status_value = "older_supported"
        warning = (
            f"Agent version {reported_version} is older than preferred backend "
            f"version {backend_version}; accepting for compatibility"
        )
    else:
        status_value = "supported"

    return AgentCompatibilityResponse(
        backend_version=backend_version,
        supported_agent_version_range=f">={MIN_SUPPORTED_AGENT_VERSION}",
        recommended_agent_version=backend_version,
        reported_agent_version=reported_version,
        status=status_value,
        warning=warning,
    )


def _policy_interval(policy: Any) -> tuple[int, int]:
    if not policy:
        return DEFAULT_HEALTH_INTERVAL_SECONDS, DEFAULT_HEALTH_JITTER_SECONDS
    interval = getattr(policy, "checkin_interval_seconds", DEFAULT_HEALTH_INTERVAL_SECONDS)
    jitter = getattr(policy, "jitter_seconds", DEFAULT_HEALTH_JITTER_SECONDS)
    return int(interval or DEFAULT_HEALTH_INTERVAL_SECONDS), int(jitter or 0)


def _agent_health(agent: Agent) -> dict[str, Any]:
    policy = getattr(agent, "policy", None)
    interval, jitter = _policy_interval(policy)
    healthy_after = interval * 2 + jitter
    offline_after = healthy_after * 4
    checked_at = _utcnow()

    if not agent.last_seen_at:
        return {
            "state": "never_seen",
            "last_seen_at": None,
            "expected_checkin_interval_seconds": interval,
            "healthy_after_seconds": healthy_after,
            "offline_after_seconds": offline_after,
            "checked_at": checked_at,
            "message": "Agent has not checked in yet",
        }

    if not agent.is_active or agent.enrollment_state in {"revoked", "rejected"}:
        return {
            "state": "offline",
            "last_seen_at": agent.last_seen_at,
            "expected_checkin_interval_seconds": interval,
            "healthy_after_seconds": healthy_after,
            "offline_after_seconds": offline_after,
            "checked_at": checked_at,
            "message": f"Agent record is {agent.enrollment_state}",
        }

    age_seconds = max(0, int((checked_at - agent.last_seen_at).total_seconds()))
    if age_seconds <= healthy_after:
        state_value = "healthy"
        message = "Agent checked in within expected policy window"
    elif age_seconds <= offline_after:
        state_value = "stale"
        message = "Agent missed the expected policy window"
    else:
        state_value = "offline"
        message = "Agent has not checked in for multiple policy windows"

    return {
        "state": state_value,
        "last_seen_at": agent.last_seen_at,
        "expected_checkin_interval_seconds": interval,
        "healthy_after_seconds": healthy_after,
        "offline_after_seconds": offline_after,
        "checked_at": checked_at,
        "message": message,
    }


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _identity_hash(observation_type: str, identity: dict[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json({"type": observation_type, "identity": identity}).encode("utf-8")
    ).hexdigest()


def _enabled_commands(policy: Optional[AgentPolicy]) -> dict[str, bool]:
    if not policy or not policy.enabled_commands:
        return {command: True for command, _ in AGENT_SECTION_POLICY.values()}
    return {
        command: bool(policy.enabled_commands.get(command, True))
        for command, _ in AGENT_SECTION_POLICY.values()
    }


def _decode_request_body(body: bytes, content_encoding: Optional[str]) -> bytes:
    if not content_encoding:
        return body
    if content_encoding.lower() != "gzip":
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported content encoding '{content_encoding}'",
        )
    try:
        return gzip.decompress(body)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid gzip payload: {exc}")


def _source_host_from_payload(payload: AgentCheckInRequest) -> Optional[str]:
    if payload.hostname:
        return payload.hostname
    if payload.addresses:
        return payload.addresses[0].ip_address
    return None


def _extract_registration_summary(payload: AgentRegistrationRequest) -> tuple[list[str], list[str], dict]:
    ips = sorted({address.ip_address for address in payload.addresses})
    macs = sorted(
        {
            address.mac_address
            for address in payload.addresses
            if address.mac_address is not None
        }
    )
    summary = {
        "address_count": len(payload.addresses),
        "ip_addresses": ips,
        "mac_addresses": macs,
        "metadata": payload.metadata or {},
    }
    return ips, macs, summary


def _merge_unique(values: Optional[list[str]], value: str) -> list[str]:
    current = list(values or [])
    if value not in current:
        current.append(value)
    return current


def _merge_unique_int(values: Optional[list[int]], value: int) -> list[int]:
    current = list(values or [])
    if value not in current:
        current.append(value)
    return current


def _agent_evidence_fact(
    host: Host,
    field_name: str,
    observed_value: Any,
    confidence: int,
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    if observed_value is None or observed_value == "":
        return None
    return {
        "entity_type": "host",
        "entity_ref": host,
        "field_name": field_name,
        "observed_value": str(observed_value),
        "confidence": confidence,
        "metadata": metadata or {},
    }


def _host_identity_evidence(
    host: Host,
    *,
    ip_address: Optional[str] = None,
    mac_address: Optional[str] = None,
    hostname: Optional[str] = None,
    fqdn: Optional[str] = None,
    vendor: Optional[str] = None,
    device_type: Optional[str] = None,
    confidence: int,
    metadata: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    facts = [
        _agent_evidence_fact(host, "ip_address", ip_address, confidence, metadata),
        _agent_evidence_fact(host, "mac_address", mac_address, confidence, metadata),
        _agent_evidence_fact(host, "hostname", hostname, confidence, metadata),
        _agent_evidence_fact(host, "fqdn", fqdn, confidence, metadata),
        _agent_evidence_fact(host, "vendor", vendor, max(confidence - 10, 0), metadata),
        _agent_evidence_fact(host, "device_type", device_type, confidence, metadata),
    ]
    return [fact for fact in facts if fact is not None]


async def _best_current_evidence_confidence(
    db: AsyncSession,
    host_id: int,
    field_name: str,
) -> int:
    result = await db.execute(
        select(func.max(EntityEvidence.confidence)).where(
            EntityEvidence.entity_type == "host",
            EntityEvidence.entity_id == host_id,
            EntityEvidence.field_name == field_name,
            EntityEvidence.is_current.is_(True),
        )
    )
    return int(result.scalar() or 0)


async def _apply_host_canonical_evidence(
    db: AsyncSession,
    host: Host,
    field_name: str,
    observed_value: str,
    confidence: int,
) -> None:
    if field_name not in {"hostname", "vendor", "device_type"}:
        return
    current_value = getattr(host, field_name, None)
    if current_value == observed_value:
        return
    if current_value:
        if host.is_verified:
            return
        origins = set(host.source_origins or [])
        if "manual" in origins and origins != {AGENT_SOURCE_ORIGIN}:
            return
        best_confidence = await _best_current_evidence_confidence(
            db,
            host.id,
            field_name,
        )
        if confidence < best_confidence:
            return
    setattr(host, field_name, observed_value)
    host.tags = merge_tags(
        host.tags,
        build_host_tags(
            ip_address=host.ip_address,
            mac_address=host.mac_address,
            hostname=host.hostname,
            fqdn=host.fqdn,
            vendor=host.vendor,
            os_family=host.os_family,
            os_name=host.os_name,
        ),
    )


async def _upsert_entity_evidence(
    db: AsyncSession,
    observation: AgentObservation,
    fact: dict[str, Any],
    observed_at: datetime,
    raw_import_id: int,
) -> bool:
    host = fact.get("entity_ref")
    entity_id = fact.get("entity_id") or getattr(host, "id", None)
    if not entity_id:
        return False

    observed_value = fact.get("observed_value")
    now = _utcnow()
    source_type = fact.get("source_type") or AGENT_SOURCE_TYPE
    result = await db.execute(
        select(EntityEvidence).where(
            EntityEvidence.entity_type == fact["entity_type"],
            EntityEvidence.entity_id == entity_id,
            EntityEvidence.field_name == fact.get("field_name"),
            EntityEvidence.observed_value == observed_value,
            EntityEvidence.source_origin == AGENT_SOURCE_ORIGIN,
            EntityEvidence.source_type == source_type,
            EntityEvidence.observer_agent_id == observation.agent_id,
            EntityEvidence.relationship_type == observation.relationship_type,
        )
    )
    evidence = result.scalar_one_or_none()
    if evidence:
        new_confidence = fact.get("confidence", evidence.confidence)
        if new_confidence >= evidence.confidence:
            evidence.confidence = new_confidence
            evidence.agent_observation_id = observation.id
            evidence.relationship_type = observation.relationship_type
            evidence.evidence_metadata = fact.get("metadata") or {}
        evidence.raw_import_id = raw_import_id
        evidence.last_seen_at = observed_at
        evidence.is_current = True
        evidence.updated_at = now
        created = False
    else:
        evidence = EntityEvidence(
            entity_type=fact["entity_type"],
            entity_id=entity_id,
            field_name=fact.get("field_name"),
            observed_value=observed_value,
            source_origin=AGENT_SOURCE_ORIGIN,
            source_type=source_type,
            observer_agent_id=observation.agent_id,
            raw_import_id=raw_import_id,
            agent_observation_id=observation.id,
            relationship_type=observation.relationship_type,
            confidence=fact.get("confidence", 50),
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            is_current=True,
            evidence_metadata=fact.get("metadata") or {},
            created_at=now,
            updated_at=now,
        )
        db.add(evidence)
        created = True

    await _apply_host_canonical_evidence(
        db,
        host,
        fact.get("field_name"),
        observed_value,
        evidence.confidence,
    )
    return created


async def _mark_observation_evidence_stale(
    db: AsyncSession,
    observation: AgentObservation,
    stale_at: datetime,
) -> int:
    result = await db.execute(
        select(EntityEvidence).where(
            EntityEvidence.agent_observation_id == observation.id,
            EntityEvidence.is_current.is_(True),
        )
    )
    stale_count = 0
    for evidence in result.scalars().all():
        evidence.is_current = False
        evidence.last_seen_at = stale_at
        evidence.updated_at = _utcnow()
        stale_count += 1
    return stale_count


def _pending_collection_request(agent: Agent) -> AgentCollectionRequestStatus:
    requested_at = agent.collection_requested_at
    fulfilled_at = agent.collection_request_fulfilled_at
    requested = bool(
        requested_at and (fulfilled_at is None or requested_at > fulfilled_at)
    )
    return AgentCollectionRequestStatus(
        requested=requested,
        requested_at=requested_at if requested else None,
        reason=agent.collection_request_reason if requested else None,
        passive_capture=(agent.collection_request_options or {}).get("passive_capture")
        if requested and agent.collection_request_options
        else None,
    )


async def _get_policy_or_404(db: AsyncSession, policy_id: int) -> AgentPolicy:
    result = await db.execute(select(AgentPolicy).where(AgentPolicy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Agent policy not found")
    return policy


async def _get_enrollment_key_or_404(
    db: AsyncSession,
    enrollment_key_id: int,
) -> AgentEnrollmentKey:
    result = await db.execute(
        select(AgentEnrollmentKey).where(AgentEnrollmentKey.id == enrollment_key_id)
    )
    enrollment_key = result.scalar_one_or_none()
    if not enrollment_key:
        raise HTTPException(status_code=404, detail="Enrollment key not found")
    return enrollment_key


async def _get_agent_or_404(db: AsyncSession, agent_id: int) -> Agent:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


async def _load_policy_map(
    db: AsyncSession,
    policy_ids: list[int],
) -> dict[int, AgentPolicy]:
    if not policy_ids:
        return {}
    result = await db.execute(
        select(AgentPolicy).where(AgentPolicy.id.in_(sorted(set(policy_ids))))
    )
    policies = result.scalars().all()
    return {policy.id: policy for policy in policies}


async def _load_enrollment_key_map(
    db: AsyncSession,
    enrollment_key_ids: list[int],
) -> dict[int, AgentEnrollmentKey]:
    if not enrollment_key_ids:
        return {}
    result = await db.execute(
        select(AgentEnrollmentKey).where(
            AgentEnrollmentKey.id.in_(sorted(set(enrollment_key_ids)))
        )
    )
    enrollment_keys = result.scalars().all()
    return {enrollment_key.id: enrollment_key for enrollment_key in enrollment_keys}


async def _attach_key_and_policy(
    agent: Agent,
    policy_map: dict[int, AgentPolicy],
    enrollment_key_map: dict[int, AgentEnrollmentKey],
) -> None:
    if agent.policy_id and agent.policy_id in policy_map:
        setattr(agent, "policy", AgentPolicyResponse.model_validate(policy_map[agent.policy_id]))
    if agent.enrollment_key_id and agent.enrollment_key_id in enrollment_key_map:
        enrollment_key = enrollment_key_map[agent.enrollment_key_id]
        if enrollment_key.default_policy_id and enrollment_key.default_policy_id in policy_map:
            setattr(
                enrollment_key,
                "default_policy",
                AgentPolicyResponse.model_validate(
                    policy_map[enrollment_key.default_policy_id]
                ),
            )
        setattr(
            agent,
            "enrollment_key",
            AgentEnrollmentKeyResponse.model_validate(enrollment_key),
        )


async def _attach_default_policy_to_enrollment_key(
    enrollment_key: AgentEnrollmentKey,
    policy_map: dict[int, AgentPolicy],
) -> None:
    if (
        enrollment_key.default_policy_id
        and enrollment_key.default_policy_id in policy_map
    ):
        setattr(
            enrollment_key,
            "default_policy",
            AgentPolicyResponse.model_validate(
                policy_map[enrollment_key.default_policy_id]
            ),
        )


async def _lookup_enrollment_key_by_secret(
    db: AsyncSession,
    raw_key: str,
) -> AgentEnrollmentKey:
    result = await db.execute(
        select(AgentEnrollmentKey).where(
            AgentEnrollmentKey.key_hash == _hash_secret(raw_key),
            AgentEnrollmentKey.is_active.is_(True),
        )
    )
    enrollment_key = result.scalar_one_or_none()
    if not enrollment_key:
        raise HTTPException(status_code=401, detail="Invalid enrollment key")

    now = _utcnow()
    if enrollment_key.expires_at and enrollment_key.expires_at < now:
        raise HTTPException(status_code=403, detail="Enrollment key has expired")
    return enrollment_key


async def _lookup_agent_by_api_key(
    db: AsyncSession,
    raw_api_key: str,
) -> Agent:
    result = await db.execute(
        select(Agent).where(
            Agent.api_key_hash == _hash_secret(raw_api_key),
            Agent.is_active.is_(True),
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid agent API key")
    if agent.enrollment_state != "active":
        raise HTTPException(
            status_code=403,
            detail=f"Agent is not approved for check-in ({agent.enrollment_state})",
        )
    return agent


async def _upsert_host(
    db: AsyncSession,
    ip_address: str,
    hostname: Optional[str] = None,
    mac_address: Optional[str] = None,
    observed_by_agent_id: Optional[int] = None,
) -> tuple[Host, bool]:
    try:
        if parse_ip(ip_address).is_unspecified:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid host IP '{ip_address}'")

    result = await db.execute(select(Host).where(Host.ip_address == ip_address))
    host = result.scalar_one_or_none()
    created = False

    if host:
        can_update_hostname = not host.hostname
        if hostname and can_update_hostname:
            host.hostname = hostname
        if mac_address and not host.mac_address:
            host.mac_address = mac_address
        current_sources = host.source_types or []
        if AGENT_SOURCE_TYPE not in current_sources:
            host.source_types = current_sources + [AGENT_SOURCE_TYPE]
        host.source_origins = _merge_unique(host.source_origins, AGENT_SOURCE_ORIGIN)
        if observed_by_agent_id is not None:
            host.observed_by_agent_ids = _merge_unique_int(
                host.observed_by_agent_ids,
                observed_by_agent_id,
            )
        host.tags = merge_tags(
            host.tags,
            build_host_tags(
                ip_address=host.ip_address,
                mac_address=host.mac_address,
                hostname=host.hostname,
                fqdn=host.fqdn,
                vendor=host.vendor,
                os_family=host.os_family,
                os_name=host.os_name,
            ),
        )
        host.last_seen = _utcnow()
        return host, created

    host = Host(
        ip_address=ip_address,
        hostname=hostname,
        mac_address=mac_address,
        source_types=[AGENT_SOURCE_TYPE],
        source_origins=[AGENT_SOURCE_ORIGIN],
        observed_by_agent_ids=[observed_by_agent_id] if observed_by_agent_id is not None else None,
        first_seen=_utcnow(),
        last_seen=_utcnow(),
    )
    host.tags = build_host_tags(
        ip_address=host.ip_address,
        mac_address=host.mac_address,
        hostname=host.hostname,
    )
    db.add(host)
    await db.flush()
    return host, True


async def _upsert_arp_entry(
    db: AsyncSession,
    ip_address: str,
    mac_address: Optional[str],
    interface: Optional[str],
    state_value: Optional[str],
    observer_agent_id: Optional[int] = None,
) -> tuple[Optional[ARPEntry], bool]:
    if not mac_address:
        return None, False

    result = await db.execute(
        select(ARPEntry).where(
            ARPEntry.ip_address == ip_address,
            ARPEntry.mac_address == mac_address,
        )
    )
    arp_entry = result.scalar_one_or_none()
    if arp_entry:
        arp_entry.interface = interface or arp_entry.interface
        arp_entry.entry_type = state_value or arp_entry.entry_type
        arp_entry.source_origin = AGENT_SOURCE_ORIGIN
        arp_entry.observer_agent_id = observer_agent_id or arp_entry.observer_agent_id
        arp_entry.last_seen = _utcnow()
        arp_entry.tags = merge_tags(
            arp_entry.tags,
            build_arp_tags(
                ip_address=arp_entry.ip_address,
                mac_address=arp_entry.mac_address,
                interface=arp_entry.interface,
                entry_type=arp_entry.entry_type,
                vendor=arp_entry.vendor,
            ),
        )
        return arp_entry, False

    arp_entry = ARPEntry(
        ip_address=ip_address,
        mac_address=mac_address,
        interface=interface,
        entry_type=state_value,
        source_type=AGENT_SOURCE_TYPE,
        source_origin=AGENT_SOURCE_ORIGIN,
        observer_agent_id=observer_agent_id,
        first_seen=_utcnow(),
        last_seen=_utcnow(),
    )
    arp_entry.tags = build_arp_tags(
        ip_address=arp_entry.ip_address,
        mac_address=arp_entry.mac_address,
        interface=arp_entry.interface,
        entry_type=arp_entry.entry_type,
        vendor=arp_entry.vendor,
    )
    db.add(arp_entry)
    await db.flush()
    return arp_entry, True


async def _upsert_connection(
    db: AsyncSession,
    local_ip: str,
    local_port: int,
    remote_ip: str,
    remote_port: Optional[int],
    protocol: str,
    state_value: Optional[str],
    pid: Optional[int],
    process_name: Optional[str],
    observer_agent_id: Optional[int] = None,
) -> tuple[Connection, bool]:
    filters = [
        Connection.local_ip == local_ip,
        Connection.local_port == local_port,
        Connection.remote_ip == remote_ip,
        Connection.protocol == protocol,
        Connection.state == state_value,
        Connection.pid == pid,
        Connection.process_name == process_name,
    ]
    if remote_port is None:
        filters.append(Connection.remote_port.is_(None))
    else:
        filters.append(Connection.remote_port == remote_port)

    result = await db.execute(select(Connection).where(*filters))
    connection = result.scalar_one_or_none()
    if connection:
        connection.source_origin = AGENT_SOURCE_ORIGIN
        connection.observer_agent_id = observer_agent_id or connection.observer_agent_id
        connection.last_seen = _utcnow()
        connection.tags = merge_tags(
            connection.tags,
            build_connection_tags(
                local_ip=connection.local_ip,
                local_port=connection.local_port,
                remote_ip=connection.remote_ip,
                remote_port=connection.remote_port,
                protocol=connection.protocol,
                state=connection.state,
                process_name=connection.process_name,
            ),
        )
        return connection, False

    connection = Connection(
        local_ip=local_ip,
        local_port=local_port,
        remote_ip=remote_ip,
        remote_port=remote_port,
        protocol=protocol,
        state=state_value,
        pid=pid,
        process_name=process_name,
        source_type=AGENT_SOURCE_TYPE,
        source_origin=AGENT_SOURCE_ORIGIN,
        observer_agent_id=observer_agent_id,
        first_seen=_utcnow(),
        last_seen=_utcnow(),
    )
    connection.tags = build_connection_tags(
        local_ip=connection.local_ip,
        local_port=connection.local_port,
        remote_ip=connection.remote_ip,
        remote_port=connection.remote_port,
        protocol=connection.protocol,
        state=connection.state,
        process_name=connection.process_name,
    )
    db.add(connection)
    await db.flush()
    return connection, True


def _policy_violation_sections(
    policy: Optional[AgentPolicy],
    payload: AgentCheckInRequest,
) -> list[tuple[str, str, int]]:
    if not policy:
        return []
    commands = _enabled_commands(policy)
    violations = []
    for section_name, (command_name, _) in AGENT_SECTION_POLICY.items():
        count = len(getattr(payload, section_name))
        if count and not commands.get(command_name, True):
            violations.append((section_name, command_name, count))
    return violations


def _raise_policy_violations(
    agent: Agent,
    policy: Optional[AgentPolicy],
    payload: AgentCheckInRequest,
) -> None:
    violations = _policy_violation_sections(policy, payload)
    if not violations:
        return

    for section_name, command_name, count in violations:
        logger.warning(
            "Rejected agent policy violation: agent_id=%s agent_uuid=%s "
            "policy_id=%s section=%s command=%s records=%s sequence=%s",
            agent.id,
            agent.agent_uuid,
            policy.id if policy else None,
            section_name,
            command_name,
            count,
            payload.sequence_number,
        )
    detail = "; ".join(
        f"{section_name} disabled by policy command {command_name} ({count} records)"
        for section_name, command_name, count in violations
    )
    raise HTTPException(status_code=403, detail=f"Agent report violates assigned policy: {detail}")


def _observation_identity(observation_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if observation_type == "address":
        return {
            "ip_address": payload.get("ip_address"),
            "interface": payload.get("interface"),
            "mac_address": payload.get("mac_address"),
        }
    if observation_type == "neighbor":
        return {
            "ip_address": payload.get("ip_address"),
            "mac_address": payload.get("mac_address"),
            "interface": payload.get("interface"),
        }
    if observation_type == "connection":
        return {
            "local_ip": payload.get("local_ip"),
            "local_port": payload.get("local_port"),
            "remote_ip": payload.get("remote_ip"),
            "remote_port": payload.get("remote_port"),
            "protocol": payload.get("protocol"),
            "state": payload.get("state"),
            "pid": payload.get("pid"),
            "process_name": payload.get("process_name"),
        }
    if observation_type == "route":
        return {
            "destination": payload.get("destination"),
            "gateway": payload.get("gateway"),
            "interface": payload.get("interface"),
            "source_ip": payload.get("source_ip"),
        }
    if observation_type == "topology_evidence":
        return {
            "evidence_type": payload.get("evidence_type"),
            "source": payload.get("source"),
            "ip_address": payload.get("ip_address"),
            "mac_address": payload.get("mac_address"),
            "hostname": payload.get("hostname"),
            "name": payload.get("name"),
            "local_ip": payload.get("local_ip"),
            "local_port": payload.get("local_port"),
            "remote_ip": payload.get("remote_ip"),
            "remote_port": payload.get("remote_port"),
            "protocol": payload.get("protocol"),
            "gateway": payload.get("gateway"),
            "destination": payload.get("destination"),
            "interface": payload.get("interface"),
            "source_ip": payload.get("source_ip"),
            "switch_ip": payload.get("switch_ip"),
            "switch_name": payload.get("switch_name"),
            "switch_port": payload.get("switch_port") or payload.get("port_id"),
            "chassis_id": payload.get("chassis_id"),
            "system_name": payload.get("system_name"),
            "management_ip": payload.get("management_ip"),
            "vlan_id": payload.get("vlan_id"),
            "network": payload.get("network"),
        }
    return payload


def _relationship_key(agent_id: int, relationship_type: Optional[str], payload: dict[str, Any]) -> Optional[str]:
    if not relationship_type:
        return None
    if relationship_type == "collector_interface":
        identity = {
            "agent_id": agent_id,
            "ip_address": payload.get("ip_address"),
            "interface": payload.get("interface"),
            "mac_address": payload.get("mac_address"),
        }
    elif relationship_type == "arp_neighbor":
        identity = {
            "agent_id": agent_id,
            "interface": payload.get("interface"),
            "ip_address": payload.get("ip_address"),
            "mac_address": payload.get("mac_address"),
        }
    elif relationship_type == "connection_remote":
        identity = {
            "agent_id": agent_id,
            "local_ip": payload.get("local_ip"),
            "remote_ip": payload.get("remote_ip"),
            "remote_port": payload.get("remote_port"),
            "protocol": payload.get("protocol"),
        }
    elif relationship_type == "route_gateway":
        identity = {
            "agent_id": agent_id,
            "source_ip": payload.get("source_ip"),
            "gateway": payload.get("gateway"),
            "destination": payload.get("destination"),
        }
    elif relationship_type in {
        "l2_neighbor",
        "switch_port_attachment",
        "mac_ip_binding",
        "dhcp_lease",
        "dns_name",
        "route",
        "flow_relationship",
        "network_segment",
    }:
        identity = {
            "agent_id": agent_id,
            **_observation_identity("topology_evidence", payload),
        }
    else:
        identity = {"agent_id": agent_id, "payload": payload}
    return _identity_hash(relationship_type, identity)


async def _upsert_agent_observation(
    db: AsyncSession,
    agent: Agent,
    observation_type: str,
    payload: dict[str, Any],
    observed_at: datetime,
    raw_import_id: int,
    checkin_id: int,
    observation_role: Optional[str] = None,
    confidence: int = 50,
    relationship_type: Optional[str] = None,
    relationship_key: Optional[str] = None,
    host_id: Optional[int] = None,
    arp_entry_id: Optional[int] = None,
    connection_id: Optional[int] = None,
) -> tuple[AgentObservation, bool, bool]:
    identity = _observation_identity(observation_type, payload)
    identity_hash = _identity_hash(observation_type, identity)
    observed_at = _naive_utc(observed_at)
    now = _utcnow()

    result = await db.execute(
        select(AgentObservation).where(
            AgentObservation.agent_id == agent.id,
            AgentObservation.observation_type == observation_type,
            AgentObservation.identity_hash == identity_hash,
        )
    )
    observation = result.scalar_one_or_none()
    if observation:
        was_removed = not observation.is_current
        observation.payload = payload
        observation.observation_role = observation_role
        observation.confidence = confidence
        observation.relationship_type = relationship_type
        observation.relationship_key = relationship_key
        observation.last_seen_at = observed_at
        observation.raw_import_id = raw_import_id
        observation.last_seen_checkin_id = checkin_id
        observation.host_id = host_id
        observation.arp_entry_id = arp_entry_id
        observation.connection_id = connection_id
        observation.is_current = True
        observation.stale_at = None
        observation.removed_at = None
        observation.updated_at = now
        return observation, False, was_removed

    observation = AgentObservation(
        agent_id=agent.id,
        raw_import_id=raw_import_id,
        last_seen_checkin_id=checkin_id,
        observation_type=observation_type,
        observation_role=observation_role,
        confidence=confidence,
        relationship_type=relationship_type,
        relationship_key=relationship_key,
        identity_hash=identity_hash,
        payload=payload,
        host_id=host_id,
        arp_entry_id=arp_entry_id,
        connection_id=connection_id,
        first_seen_at=observed_at,
        last_seen_at=observed_at,
        is_current=True,
        created_at=now,
        updated_at=now,
    )
    db.add(observation)
    return observation, True, False


async def _mark_stale_observations(
    db: AsyncSession,
    agent: Agent,
    observation_type: str,
    current_hashes: set[str],
    stale_at: datetime,
) -> int:
    result = await db.execute(
        select(AgentObservation).where(
            AgentObservation.agent_id == agent.id,
            AgentObservation.observation_type == observation_type,
            AgentObservation.is_current.is_(True),
        )
    )
    stale_count = 0
    for observation in result.scalars().all():
        if observation.identity_hash in current_hashes:
            continue
        observation.is_current = False
        observation.stale_at = stale_at
        observation.removed_at = None
        observation.updated_at = _utcnow()
        await _mark_observation_evidence_stale(db, observation, stale_at)
        stale_count += 1
    return stale_count


def _is_usable_host_ip(value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        return not parse_ip(value).is_unspecified
    except ValueError:
        return False


def _topology_summary(payload: dict[str, Any]) -> str:
    evidence_type = payload.get("evidence_type") or "topology_evidence"
    if evidence_type == "flow_relationship":
        return (
            f"{payload.get('local_ip') or '?'}:{payload.get('local_port') or '?'} -> "
            f"{payload.get('remote_ip') or '?'}:{payload.get('remote_port') or '?'}"
        )
    if evidence_type == "route":
        return f"{payload.get('source_ip') or '?'} -> {payload.get('destination') or '?'} via {payload.get('gateway') or '?'}"
    if evidence_type == "dns_name":
        return f"{payload.get('ip_address') or '?'} -> {payload.get('name') or payload.get('hostname') or '?'}"
    if evidence_type == "network_segment":
        return f"{payload.get('network') or '?'} vlan={payload.get('vlan_id') or '?'}"
    if evidence_type == "switch_port_attachment":
        return (
            f"{payload.get('mac_address') or payload.get('ip_address') or '?'} on "
            f"{payload.get('switch_name') or payload.get('switch_ip') or '?'} "
            f"{payload.get('switch_port') or payload.get('port_id') or '?'}"
        )
    if evidence_type == "l2_neighbor":
        return (
            f"{payload.get('system_name') or payload.get('chassis_id') or '?'} "
            f"port {payload.get('port_id') or '?'}"
        )
    if evidence_type in {"mac_ip_binding", "dhcp_lease"}:
        return f"{payload.get('mac_address') or '?'} -> {payload.get('ip_address') or '?'}"
    return json.dumps(payload, sort_keys=True, default=str)[:500]


def _topology_metadata(payload: dict[str, Any], role: str) -> dict[str, Any]:
    return {
        "observation_role": role,
        "evidence_type": payload.get("evidence_type"),
        "source": payload.get("source"),
        "observer": payload.get("observer"),
        "raw_ref": payload.get("raw_ref"),
        "raw": payload.get("metadata") or {},
    }


def _topology_fact(
    host: Optional[Host],
    payload: dict[str, Any],
    field_name: Optional[str],
    observed_value: Any,
    *,
    confidence: int,
    role: str,
) -> Optional[dict[str, Any]]:
    if host is None or observed_value is None or observed_value == "":
        return None
    return {
        "entity_type": "host",
        "entity_ref": host,
        "field_name": field_name,
        "observed_value": str(observed_value),
        "confidence": confidence,
        "source_type": payload.get("source") or AGENT_SOURCE_TYPE,
        "metadata": _topology_metadata(payload, role),
    }


async def _topology_host(
    db: AsyncSession,
    agent: Agent,
    ip_address: Optional[str],
    *,
    hostname: Optional[str] = None,
    mac_address: Optional[str] = None,
) -> tuple[Optional[Host], bool]:
    if not _is_usable_host_ip(ip_address):
        return None, False
    return await _upsert_host(
        db,
        ip_address,
        hostname=hostname,
        mac_address=mac_address,
        observed_by_agent_id=agent.id,
    )


async def _ingest_agent_payload(
    db: AsyncSession,
    agent: Agent,
    payload: AgentCheckInRequest,
    decoded_body: bytes,
    content_encoding: Optional[str],
    source_ip: Optional[str],
    policy: Optional[AgentPolicy],
) -> tuple[AgentCheckIn, RawImport, AgentPolicyResponse | None, dict]:
    now = _utcnow()
    observed_at = _naive_utc(payload.observed_at)
    effective_full_snapshot = payload.full_snapshot
    if not effective_full_snapshot:
        logger.warning(
            "Accepted legacy partial agent report without stale/removal marking: "
            "agent_id=%s agent_uuid=%s sequence=%s reported_version=%s",
            agent.id,
            agent.agent_uuid,
            payload.sequence_number,
            payload.agent_version,
        )
    host_creates = 0
    arp_creates = 0
    connection_creates = 0
    observation_creates = 0
    observation_refreshes = 0
    observation_reactivations = 0
    observation_stale = 0
    observation_removals = 0
    evidence_creates = 0
    evidence_refreshes = 0

    seen_ips: set[str] = set()
    seen_macs: set[str] = set()
    observation_inputs: list[dict[str, Any]] = []
    current_hashes: dict[str, set[str]] = {
        "address": set(),
        "neighbor": set(),
        "connection": set(),
        "route": set(),
        "topology_evidence": set(),
    }
    agent_self_ips = {
        address.ip_address
        for address in payload.addresses
        if not parse_ip(address.ip_address).is_unspecified
    }

    for address in payload.addresses:
        vendor = lookup_mac_vendor(address.mac_address) if address.mac_address else None
        host, created = await _upsert_host(
            db,
            address.ip_address,
            hostname=payload.hostname,
            mac_address=address.mac_address,
            observed_by_agent_id=agent.id,
        )
        host_creates += int(created)
        seen_ips.add(address.ip_address)
        if address.mac_address:
            seen_macs.add(address.mac_address)
        address_payload = address.model_dump(mode="json")
        current_hashes["address"].add(
            _identity_hash("address", _observation_identity("address", address_payload))
        )
        observation_inputs.append(
            {
                "type": "address",
                "payload": address_payload,
                "observation_role": "agent_self_interface",
                "confidence": 95,
                "relationship_type": "collector_interface",
                "host_ref": host,
                "evidence": _host_identity_evidence(
                    host,
                    ip_address=address.ip_address,
                    mac_address=address.mac_address,
                    hostname=payload.hostname,
                    fqdn=payload.fqdn,
                    vendor=vendor,
                    confidence=95,
                    metadata={
                        "observation_role": "agent_self_interface",
                        "interface": address.interface,
                    },
                ),
            }
        )

    for neighbor in payload.neighbors:
        vendor = lookup_mac_vendor(neighbor.mac_address) if neighbor.mac_address else None
        host, created = await _upsert_host(
            db,
            neighbor.ip_address,
            hostname=neighbor.hostname,
            mac_address=neighbor.mac_address,
            observed_by_agent_id=agent.id,
        )
        host_creates += int(created)
        arp_entry, arp_created = await _upsert_arp_entry(
            db,
            neighbor.ip_address,
            neighbor.mac_address,
            neighbor.interface,
            neighbor.state,
            observer_agent_id=agent.id,
        )
        arp_creates += int(arp_created)
        seen_ips.add(neighbor.ip_address)
        if neighbor.mac_address:
            seen_macs.add(neighbor.mac_address)
        neighbor_payload = neighbor.model_dump(mode="json")
        current_hashes["neighbor"].add(
            _identity_hash("neighbor", _observation_identity("neighbor", neighbor_payload))
        )
        observation_inputs.append(
            {
                "type": "neighbor",
                "payload": neighbor_payload,
                "observation_role": "arp_neighbor",
                "confidence": 80,
                "relationship_type": "arp_neighbor",
                "host_ref": host,
                "arp_entry_id": arp_entry.id if arp_entry else None,
                "evidence": _host_identity_evidence(
                    host,
                    ip_address=neighbor.ip_address,
                    mac_address=neighbor.mac_address,
                    hostname=neighbor.hostname,
                    vendor=vendor,
                    confidence=80,
                    metadata={
                        "observation_role": "arp_neighbor",
                        "interface": neighbor.interface,
                        "neighbor_state": neighbor.state,
                    },
                ),
            }
        )

    for route in payload.routes:
        route_host = None
        route_evidence: list[dict[str, Any]] = []
        if route.source_ip:
            if not parse_ip(route.source_ip).is_unspecified:
                host, created = await _upsert_host(
                    db,
                    route.source_ip,
                    hostname=payload.hostname if route.source_ip in agent_self_ips else None,
                    observed_by_agent_id=agent.id,
                )
                route_host = host
                host_creates += int(created)
                seen_ips.add(route.source_ip)
                route_evidence.extend(
                    _host_identity_evidence(
                        host,
                        ip_address=route.source_ip,
                        hostname=payload.hostname if route.source_ip in agent_self_ips else None,
                        confidence=70 if route.source_ip in agent_self_ips else 55,
                        metadata={
                            "observation_role": "route_source",
                            "interface": route.interface,
                            "destination": route.destination,
                        },
                    )
                )
        if route.gateway:
            if not parse_ip(route.gateway).is_unspecified:
                gateway_host, created = await _upsert_host(
                    db,
                    route.gateway,
                    observed_by_agent_id=agent.id,
                )
                host_creates += int(created)
                seen_ips.add(route.gateway)
                route_evidence.extend(
                    _host_identity_evidence(
                        gateway_host,
                        ip_address=route.gateway,
                        device_type="router",
                        confidence=70,
                        metadata={
                            "observation_role": "route_gateway",
                            "interface": route.interface,
                            "destination": route.destination,
                            "source_ip": route.source_ip,
                        },
                    )
                )
        route_payload = route.model_dump(mode="json")
        current_hashes["route"].add(
            _identity_hash("route", _observation_identity("route", route_payload))
        )
        observation_inputs.append(
            {
                "type": "route",
                "payload": route_payload,
                "observation_role": "route_gateway" if route.gateway else "route_source",
                "confidence": 70 if route.gateway else 55,
                "relationship_type": "route_gateway" if route.gateway else None,
                "host_ref": route_host,
                "evidence": route_evidence,
            }
        )

    for connection in payload.connections:
        connection_host = None
        connection_evidence: list[dict[str, Any]] = []
        if not parse_ip(connection.local_ip).is_unspecified:
            host, created = await _upsert_host(
                db,
                connection.local_ip,
                hostname=payload.hostname if connection.local_ip in agent_self_ips else None,
                observed_by_agent_id=agent.id,
            )
            connection_host = host
            host_creates += int(created)
            seen_ips.add(connection.local_ip)
            local_confidence = 60 if connection.local_ip in agent_self_ips else 35
            connection_evidence.extend(
                _host_identity_evidence(
                    host,
                    ip_address=connection.local_ip,
                    hostname=payload.hostname if connection.local_ip in agent_self_ips else None,
                    confidence=local_confidence,
                    metadata={
                        "observation_role": (
                            "connection_local"
                            if connection.local_ip in agent_self_ips
                            else "connection_remote"
                        ),
                        "local_port": connection.local_port,
                        "remote_ip": connection.remote_ip,
                        "remote_port": connection.remote_port,
                        "protocol": connection.protocol,
                    },
                )
            )
        if not parse_ip(connection.remote_ip).is_unspecified:
            remote_host, remote_created = await _upsert_host(
                db,
                connection.remote_ip,
                observed_by_agent_id=agent.id,
            )
            host_creates += int(remote_created)
            seen_ips.add(connection.remote_ip)
            connection_evidence.extend(
                _host_identity_evidence(
                    remote_host,
                    ip_address=connection.remote_ip,
                    confidence=35,
                    metadata={
                        "observation_role": "connection_remote",
                        "local_ip": connection.local_ip,
                        "local_port": connection.local_port,
                        "remote_port": connection.remote_port,
                        "protocol": connection.protocol,
                    },
                )
            )
        db_connection, connection_created = await _upsert_connection(
            db,
            local_ip=connection.local_ip,
            local_port=connection.local_port,
            remote_ip=connection.remote_ip,
            remote_port=connection.remote_port,
            protocol=connection.protocol,
            state_value=connection.state,
            pid=connection.pid,
            process_name=connection.process_name,
            observer_agent_id=agent.id,
        )
        connection_creates += int(connection_created)
        connection_payload = connection.model_dump(mode="json")
        current_hashes["connection"].add(
            _identity_hash(
                "connection",
                _observation_identity("connection", connection_payload),
            )
        )
        observation_inputs.append(
            {
                "type": "connection",
                "payload": connection_payload,
                "observation_role": (
                    "connection_local"
                    if connection.local_ip in agent_self_ips
                    else "connection_remote"
                ),
                "confidence": 60 if connection.local_ip in agent_self_ips else 35,
                "relationship_type": "connection_remote",
                "host_ref": connection_host,
                "connection_id": db_connection.id,
                "evidence": connection_evidence,
            }
        )

    for topology_item in payload.topology_evidence:
        topology_payload = topology_item.model_dump(mode="json")
        evidence_type = topology_payload["evidence_type"]
        confidence = int(topology_payload.get("confidence") or 50)
        relationship_type = evidence_type
        topology_role = evidence_type
        topology_host_ref = None
        topology_host_id = None
        topology_connection_id = None
        topology_arp_id = None
        topology_evidence: list[dict[str, Any]] = []
        item_host_creates = 0

        primary_name = (
            topology_payload.get("hostname")
            or topology_payload.get("fqdn")
            or topology_payload.get("name")
        )
        primary_host, created = await _topology_host(
            db,
            agent,
            topology_payload.get("ip_address"),
            hostname=primary_name if evidence_type in {"dhcp_lease", "mac_ip_binding"} else None,
            mac_address=topology_payload.get("mac_address"),
        )
        item_host_creates += int(created)
        if primary_host:
            topology_host_ref = primary_host
            topology_host_id = primary_host.id
            seen_ips.add(primary_host.ip_address)
            if topology_payload.get("mac_address"):
                seen_macs.add(topology_payload["mac_address"])
            topology_evidence.extend(
                _host_identity_evidence(
                    primary_host,
                    ip_address=topology_payload.get("ip_address"),
                    mac_address=topology_payload.get("mac_address"),
                    hostname=(
                        primary_name
                        if evidence_type in {"dhcp_lease", "mac_ip_binding"}
                        else None
                    ),
                    fqdn=topology_payload.get("fqdn"),
                    confidence=confidence,
                    metadata=_topology_metadata(topology_payload, topology_role),
                )
            )

        if evidence_type in {"mac_ip_binding", "dhcp_lease"} and topology_payload.get("ip_address"):
            arp_entry, arp_created = await _upsert_arp_entry(
                db,
                topology_payload["ip_address"],
                topology_payload.get("mac_address"),
                topology_payload.get("interface"),
                evidence_type,
                observer_agent_id=agent.id,
            )
            topology_arp_id = arp_entry.id if arp_entry else None
            arp_creates += int(arp_created)
            if primary_host:
                topology_evidence.append(
                    _topology_fact(
                        primary_host,
                        topology_payload,
                        "mac_ip_binding" if evidence_type == "mac_ip_binding" else "dhcp_lease",
                        _topology_summary(topology_payload),
                        confidence=confidence,
                        role=topology_role,
                    )
                )

        if evidence_type == "dns_name" and primary_host:
            dns_value = topology_payload.get("name") or topology_payload.get("hostname") or topology_payload.get("fqdn")
            topology_evidence.append(
                _topology_fact(
                    primary_host,
                    topology_payload,
                    "dns_name",
                    dns_value,
                    confidence=confidence,
                    role=topology_role,
                )
            )

        if evidence_type == "route":
            source_host, created = await _topology_host(
                db,
                agent,
                topology_payload.get("source_ip"),
            )
            item_host_creates += int(created)
            gateway_host, created = await _topology_host(
                db,
                agent,
                topology_payload.get("gateway"),
            )
            item_host_creates += int(created)
            if source_host:
                topology_host_ref = source_host
                topology_host_id = source_host.id
                seen_ips.add(source_host.ip_address)
                topology_evidence.append(
                    _topology_fact(
                        source_host,
                        topology_payload,
                        "route",
                        _topology_summary(topology_payload),
                        confidence=confidence,
                        role="route_source",
                    )
                )
            if gateway_host:
                seen_ips.add(gateway_host.ip_address)
                topology_evidence.extend(
                    _host_identity_evidence(
                        gateway_host,
                        ip_address=topology_payload.get("gateway"),
                        device_type="router",
                        confidence=max(confidence, 70),
                        metadata=_topology_metadata(topology_payload, "route_gateway"),
                    )
                )

        if evidence_type == "flow_relationship":
            local_host, created = await _topology_host(
                db,
                agent,
                topology_payload.get("local_ip"),
            )
            item_host_creates += int(created)
            remote_host, created = await _topology_host(
                db,
                agent,
                topology_payload.get("remote_ip"),
            )
            item_host_creates += int(created)
            if local_host:
                topology_host_ref = local_host
                topology_host_id = local_host.id
                seen_ips.add(local_host.ip_address)
                topology_evidence.append(
                    _topology_fact(
                        local_host,
                        topology_payload,
                        "flow_relationship",
                        _topology_summary(topology_payload),
                        confidence=confidence,
                        role="flow_local",
                    )
                )
            if remote_host:
                seen_ips.add(remote_host.ip_address)
            if (
                _is_usable_host_ip(topology_payload.get("local_ip"))
                and _is_usable_host_ip(topology_payload.get("remote_ip"))
                and topology_payload.get("local_port") is not None
                and topology_payload.get("protocol")
            ):
                db_connection, connection_created = await _upsert_connection(
                    db,
                    local_ip=topology_payload["local_ip"],
                    local_port=topology_payload["local_port"],
                    remote_ip=topology_payload["remote_ip"],
                    remote_port=topology_payload.get("remote_port"),
                    protocol=topology_payload["protocol"],
                    state_value="established",
                    pid=None,
                    process_name=None,
                    observer_agent_id=agent.id,
                )
                topology_connection_id = db_connection.id
                connection_creates += int(connection_created)

        if evidence_type == "l2_neighbor":
            neighbor_host, created = await _topology_host(
                db,
                agent,
                topology_payload.get("management_ip") or topology_payload.get("switch_ip"),
                hostname=topology_payload.get("system_name") or topology_payload.get("switch_name"),
            )
            item_host_creates += int(created)
            if neighbor_host:
                topology_host_ref = neighbor_host
                topology_host_id = neighbor_host.id
                seen_ips.add(neighbor_host.ip_address)
                topology_evidence.extend(
                    _host_identity_evidence(
                        neighbor_host,
                        ip_address=neighbor_host.ip_address,
                        hostname=topology_payload.get("system_name") or topology_payload.get("switch_name"),
                        device_type="switch",
                        confidence=confidence,
                        metadata=_topology_metadata(topology_payload, topology_role),
                    )
                )
            if topology_host_ref:
                topology_evidence.append(
                    _topology_fact(
                        topology_host_ref,
                        topology_payload,
                        "l2_neighbor",
                        _topology_summary(topology_payload),
                        confidence=confidence,
                        role=topology_role,
                    )
                )

        if evidence_type == "switch_port_attachment":
            attached_host, created = await _topology_host(
                db,
                agent,
                topology_payload.get("ip_address"),
                hostname=topology_payload.get("hostname"),
                mac_address=topology_payload.get("mac_address"),
            )
            item_host_creates += int(created)
            switch_host, created = await _topology_host(
                db,
                agent,
                topology_payload.get("switch_ip") or topology_payload.get("management_ip"),
                hostname=topology_payload.get("switch_name") or topology_payload.get("system_name"),
            )
            item_host_creates += int(created)
            if attached_host:
                topology_host_ref = attached_host
                topology_host_id = attached_host.id
                seen_ips.add(attached_host.ip_address)
                topology_evidence.append(
                    _topology_fact(
                        attached_host,
                        topology_payload,
                        "switch_port_attachment",
                        _topology_summary(topology_payload),
                        confidence=confidence,
                        role=topology_role,
                    )
                )
            if switch_host:
                seen_ips.add(switch_host.ip_address)
                topology_evidence.extend(
                    _host_identity_evidence(
                        switch_host,
                        ip_address=switch_host.ip_address,
                        hostname=topology_payload.get("switch_name") or topology_payload.get("system_name"),
                        device_type="switch",
                        confidence=confidence,
                        metadata=_topology_metadata(topology_payload, "switch"),
                    )
                )

        if evidence_type == "network_segment":
            if primary_host:
                topology_evidence.append(
                    _topology_fact(
                        primary_host,
                        topology_payload,
                        "network_segment",
                        _topology_summary(topology_payload),
                        confidence=confidence,
                        role=topology_role,
                    )
                )
            else:
                topology_host_id = None

        host_creates += item_host_creates
        topology_evidence = [item for item in topology_evidence if item is not None]
        current_hashes["topology_evidence"].add(
            _identity_hash(
                "topology_evidence",
                _observation_identity("topology_evidence", topology_payload),
            )
        )
        observation_inputs.append(
            {
                "type": "topology_evidence",
                "payload": topology_payload,
                "observation_role": topology_role,
                "confidence": confidence,
                "relationship_type": relationship_type,
                "host_ref": topology_host_ref,
                "host_id": topology_host_id,
                "arp_entry_id": topology_arp_id,
                "connection_id": topology_connection_id,
                "evidence": topology_evidence,
            }
        )

    raw_import = RawImport(
        source_type=AGENT_SOURCE_TYPE,
        source_origin=AGENT_SOURCE_ORIGIN,
        import_type=AGENT_IMPORT_TYPE,
        filename=f"{agent.agent_uuid}-{payload.observed_at.isoformat()}.json",
        source_host=_source_host_from_payload(payload),
        raw_data=decoded_body.decode("utf-8"),
        tags=["agent", f"agent_uuid:{agent.agent_uuid}"],
        notes="Passive agent check-in",
        parse_status="success",
        parsed_count=0,
        parse_results={},
        created_at=now,
        processed_at=now,
    )
    db.add(raw_import)
    await db.flush()

    checkin = AgentCheckIn(
        agent_id=agent.id,
        raw_import_id=raw_import.id,
        observed_at=observed_at,
        received_at=now,
        sequence_number=payload.sequence_number,
        full_snapshot=effective_full_snapshot,
        content_encoding=content_encoding or "identity",
        source_ip=source_ip,
        auth_method="api_key",
        api_key_prefix=agent.api_key_prefix,
        report=payload.model_dump(mode="json"),
        summary={},
        status="accepted",
        records_created=0,
    )
    db.add(checkin)
    await db.flush()

    for observation_input in observation_inputs:
        observation, created, reactivated = await _upsert_agent_observation(
            db=db,
            agent=agent,
            observation_type=observation_input["type"],
            payload=observation_input["payload"],
            observed_at=observed_at,
            raw_import_id=raw_import.id,
            checkin_id=checkin.id,
            observation_role=observation_input.get("observation_role"),
            confidence=observation_input.get("confidence", 50),
            relationship_type=observation_input.get("relationship_type"),
            relationship_key=_relationship_key(
                agent.id,
                observation_input.get("relationship_type"),
                observation_input["payload"],
            ),
            host_id=observation_input.get("host_id")
            or getattr(observation_input.get("host_ref"), "id", None),
            arp_entry_id=observation_input.get("arp_entry_id"),
            connection_id=observation_input.get("connection_id"),
        )
        await db.flush()
        current_hashes[observation.observation_type].add(observation.identity_hash)
        observation_creates += int(created)
        observation_refreshes += int(not created)
        observation_reactivations += int(reactivated)
        for evidence_fact in observation_input.get("evidence", []):
            evidence_created = await _upsert_entity_evidence(
                db,
                observation,
                evidence_fact,
                observed_at,
                raw_import.id,
            )
            evidence_creates += int(evidence_created)
            evidence_refreshes += int(not evidence_created)

    commands = _enabled_commands(policy)
    if effective_full_snapshot:
        for _, (command_name, observation_type) in AGENT_SECTION_POLICY.items():
            if commands.get(command_name, True):
                observation_stale += await _mark_stale_observations(
                    db,
                    agent,
                    observation_type,
                    current_hashes[observation_type],
                    now,
                )

    summary = {
        "hosts_created": host_creates,
        "arp_entries_created": arp_creates,
        "connections_created": connection_creates,
        "observations_created": observation_creates,
        "observations_refreshed": observation_refreshes,
        "observations_reactivated": observation_reactivations,
        "observations_stale": observation_stale,
        "observations_removed": observation_removals,
        "evidence_created": evidence_creates,
        "evidence_refreshed": evidence_refreshes,
        "ip_addresses_seen": sorted(seen_ips),
        "mac_addresses_seen": sorted(seen_macs),
        "address_count": len(payload.addresses),
        "neighbor_count": len(payload.neighbors),
        "connection_count": len(payload.connections),
        "route_count": len(payload.routes),
        "topology_evidence_count": len(payload.topology_evidence),
        "raw_import_id": raw_import.id,
        "full_snapshot": effective_full_snapshot,
        "reported_full_snapshot": payload.full_snapshot,
    }
    raw_import.parsed_count = host_creates + arp_creates + connection_creates
    raw_import.parse_results = {
        "observed_at": observed_at.isoformat(),
        "sequence_number": payload.sequence_number,
        "full_snapshot": effective_full_snapshot,
        "reported_full_snapshot": payload.full_snapshot,
        "counts": summary,
        "content_encoding": content_encoding or "identity",
        "auth_method": "api_key",
    }
    checkin.summary = summary
    checkin.records_created = host_creates + arp_creates + connection_creates

    agent.hostname = payload.hostname or agent.hostname
    agent.agent_version = payload.agent_version or agent.agent_version
    agent.platform = payload.platform or agent.platform
    agent.platform_release = payload.platform_release or agent.platform_release
    agent.last_ip_addresses = sorted(seen_ips)
    agent.last_mac_addresses = sorted(seen_macs)
    agent.last_checkin_summary = summary
    agent.last_seen_at = now
    if (
        agent.collection_requested_at
        and (
            agent.collection_request_fulfilled_at is None
            or agent.collection_requested_at > agent.collection_request_fulfilled_at
        )
    ):
        agent.collection_request_fulfilled_at = now
        agent.collection_request_options = None

    await db.flush()

    return (
        checkin,
        raw_import,
        AgentPolicyResponse.model_validate(policy) if policy else None,
        summary,
    )


def _agent_response(agent: Agent) -> AgentResponse:
    response = AgentResponse.model_validate(agent)
    response.health = AgentHealthResponse(**_agent_health(agent))
    response.compatibility = _agent_compatibility(agent.agent_version)
    return response


@router.get("/policies", response_model=PaginatedResponse)
async def list_policies(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    is_active: Optional[bool] = Query(None),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(AgentPolicy)
    count_query = select(func.count(AgentPolicy.id))

    if is_active is not None:
        query = query.where(AgentPolicy.is_active == is_active)
        count_query = count_query.where(AgentPolicy.is_active == is_active)

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(AgentPolicy.name.asc()).offset(skip).limit(limit)
    )
    policies = result.scalars().all()

    policy_ids = [policy.id for policy in policies]
    counts: dict[int, int] = {}
    if policy_ids:
        count_rows = await db.execute(
            select(Agent.policy_id, func.count(Agent.id))
            .where(Agent.policy_id.in_(policy_ids))
            .group_by(Agent.policy_id)
        )
        counts = {row[0]: row[1] for row in count_rows.all()}

    for policy in policies:
        setattr(policy, "agent_count", counts.get(policy.id, 0))

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [AgentPolicyResponse.model_validate(policy) for policy in policies],
    }


@router.post("/policies", response_model=AgentPolicyResponse, status_code=201)
async def create_policy(
    policy: AgentPolicyCreate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    db_policy = AgentPolicy(**policy.model_dump())
    db.add(db_policy)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Agent policy name already exists")

    await db.refresh(db_policy)
    audit.log(
        action="CREATE",
        actor="user",
        resource="AgentPolicy",
        resource_id=str(db_policy.id),
        status="success",
        details={"name": db_policy.name},
    )
    return AgentPolicyResponse.model_validate(db_policy)


@router.patch("/policies/{policy_id}", response_model=AgentPolicyResponse)
async def update_policy(
    policy_id: int,
    policy_update: AgentPolicyUpdate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    policy = await _get_policy_or_404(db, policy_id)

    for field, value in policy_update.model_dump(exclude_unset=True).items():
        setattr(policy, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Agent policy name already exists")

    await db.refresh(policy)
    audit.log(
        action="UPDATE",
        actor="user",
        resource="AgentPolicy",
        resource_id=str(policy.id),
        status="success",
        details={"name": policy.name},
    )
    return AgentPolicyResponse.model_validate(policy)


@router.get("/enrollment-keys", response_model=PaginatedResponse)
async def list_enrollment_keys(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    is_active: Optional[bool] = Query(None),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(AgentEnrollmentKey)
    count_query = select(func.count(AgentEnrollmentKey.id))
    if is_active is not None:
        query = query.where(AgentEnrollmentKey.is_active == is_active)
        count_query = count_query.where(AgentEnrollmentKey.is_active == is_active)

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(AgentEnrollmentKey.name.asc()).offset(skip).limit(limit)
    )
    enrollment_keys = result.scalars().all()
    policy_map = await _load_policy_map(
        db,
        [
            enrollment_key.default_policy_id
            for enrollment_key in enrollment_keys
            if enrollment_key.default_policy_id
        ],
    )
    for enrollment_key in enrollment_keys:
        await _attach_default_policy_to_enrollment_key(enrollment_key, policy_map)

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [
            AgentEnrollmentKeyResponse.model_validate(enrollment_key)
            for enrollment_key in enrollment_keys
        ],
    }


@router.post(
    "/enrollment-keys",
    response_model=AgentEnrollmentKeyCreateResponse,
    status_code=201,
)
async def create_enrollment_key(
    enrollment_key: AgentEnrollmentKeyCreate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if enrollment_key.default_policy_id is not None:
        await _get_policy_or_404(db, enrollment_key.default_policy_id)

    raw_key, key_prefix = _generate_secret(ENROLLMENT_KEY_PREFIX)
    db_enrollment_key = AgentEnrollmentKey(
        **enrollment_key.model_dump(),
        key_hash=_hash_secret(raw_key),
        key_prefix=key_prefix,
    )
    db.add(db_enrollment_key)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Enrollment key name already exists")

    await db.refresh(db_enrollment_key)
    if db_enrollment_key.default_policy_id:
        policy_map = await _load_policy_map(db, [db_enrollment_key.default_policy_id])
        await _attach_default_policy_to_enrollment_key(db_enrollment_key, policy_map)

    audit.log(
        action="CREATE",
        actor="user",
        resource="AgentEnrollmentKey",
        resource_id=str(db_enrollment_key.id),
        status="success",
        details={"name": db_enrollment_key.name},
    )
    return AgentEnrollmentKeyCreateResponse(
        enrollment_key=raw_key,
        key=AgentEnrollmentKeyResponse.model_validate(db_enrollment_key),
    )


@router.patch("/enrollment-keys/{enrollment_key_id}", response_model=AgentEnrollmentKeyResponse)
async def update_enrollment_key(
    enrollment_key_id: int,
    enrollment_key_update: AgentEnrollmentKeyUpdate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    enrollment_key = await _get_enrollment_key_or_404(db, enrollment_key_id)
    update_data = enrollment_key_update.model_dump(exclude_unset=True)

    if "default_policy_id" in update_data and update_data["default_policy_id"] is not None:
        await _get_policy_or_404(db, update_data["default_policy_id"])

    for field, value in update_data.items():
        setattr(enrollment_key, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Enrollment key name already exists")

    await db.refresh(enrollment_key)
    if enrollment_key.default_policy_id:
        policy_map = await _load_policy_map(db, [enrollment_key.default_policy_id])
        await _attach_default_policy_to_enrollment_key(enrollment_key, policy_map)

    audit.log(
        action="UPDATE",
        actor="user",
        resource="AgentEnrollmentKey",
        resource_id=str(enrollment_key.id),
        status="success",
        details={"name": enrollment_key.name},
    )
    return AgentEnrollmentKeyResponse.model_validate(enrollment_key)


@router.get("", response_model=PaginatedResponse)
async def list_agents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    enrollment_state: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(Agent)
    count_query = select(func.count(Agent.id))

    if enrollment_state:
        query = query.where(Agent.enrollment_state == enrollment_state.lower())
        count_query = count_query.where(Agent.enrollment_state == enrollment_state.lower())
    if is_active is not None:
        query = query.where(Agent.is_active == is_active)
        count_query = count_query.where(Agent.is_active == is_active)

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(Agent.last_seen_at.is_(None), Agent.last_seen_at.desc(), Agent.id.desc())
        .offset(skip)
        .limit(limit)
    )
    agents = result.scalars().all()
    policy_map = await _load_policy_map(
        db,
        [agent.policy_id for agent in agents if agent.policy_id],
    )
    enrollment_key_map = await _load_enrollment_key_map(
        db,
        [agent.enrollment_key_id for agent in agents if agent.enrollment_key_id],
    )
    default_policy_map = await _load_policy_map(
        db,
        [
            enrollment_key.default_policy_id
            for enrollment_key in enrollment_key_map.values()
            if enrollment_key.default_policy_id
        ],
    )
    policy_map.update(default_policy_map)
    for agent in agents:
        await _attach_key_and_policy(agent, policy_map, enrollment_key_map)

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [_agent_response(agent) for agent in agents],
    }


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    agent: AgentCreate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if agent.policy_id is not None:
        await _get_policy_or_404(db, agent.policy_id)
    if agent.enrollment_key_id is not None:
        await _get_enrollment_key_or_404(db, agent.enrollment_key_id)

    db_agent = Agent(**agent.model_dump())
    db.add(db_agent)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Agent UUID already exists")

    await db.refresh(db_agent)
    policy_map = await _load_policy_map(
        db,
        [db_agent.policy_id] if db_agent.policy_id else [],
    )
    enrollment_key_map = await _load_enrollment_key_map(
        db,
        [db_agent.enrollment_key_id] if db_agent.enrollment_key_id else [],
    )
    default_policy_map = await _load_policy_map(
        db,
        [
            enrollment_key.default_policy_id
            for enrollment_key in enrollment_key_map.values()
            if enrollment_key.default_policy_id
        ],
    )
    policy_map.update(default_policy_map)
    await _attach_key_and_policy(db_agent, policy_map, enrollment_key_map)

    audit.log(
        action="CREATE",
        actor="user",
        resource="Agent",
        resource_id=str(db_agent.id),
        status="success",
        details={"agent_uuid": db_agent.agent_uuid},
    )
    return _agent_response(db_agent)


@router.post("/register", response_model=AgentRegistrationResponse)
async def register_agent(
    registration: AgentRegistrationRequest,
    db: AsyncSession = Depends(get_db),
):
    enrollment_key = await _lookup_enrollment_key_by_secret(db, registration.enrollment_key)
    now = _utcnow()
    ip_addresses, mac_addresses, registration_summary = _extract_registration_summary(registration)

    result = await db.execute(select(Agent).where(Agent.agent_uuid == registration.agent_uuid))
    agent = result.scalar_one_or_none()
    created = False
    issued_api_key: Optional[str] = None

    if agent and agent.enrollment_state in {"rejected", "revoked"}:
        raise HTTPException(
            status_code=403,
            detail=f"Agent registration is {agent.enrollment_state}",
        )

    if agent and agent.enrollment_key_id not in (None, enrollment_key.id):
        raise HTTPException(
            status_code=409,
            detail="Agent UUID is already associated with a different enrollment key",
        )

    if (
        agent is None
        and enrollment_key.max_registrations is not None
        and enrollment_key.registration_count >= enrollment_key.max_registrations
    ):
        raise HTTPException(
            status_code=403,
            detail="Enrollment key registration limit reached",
        )

    if agent is None:
        agent = Agent(
            agent_uuid=registration.agent_uuid,
            display_name=registration.display_name,
            hostname=registration.hostname,
            site_name=registration.site_name,
            enrollment_key_id=enrollment_key.id,
            policy_id=enrollment_key.default_policy_id,
            enrollment_state="active" if enrollment_key.auto_approve else "pending",
            approval_required=not enrollment_key.auto_approve,
            agent_version=registration.agent_version,
            platform=registration.platform,
            platform_release=registration.platform_release,
            last_registration_at=now,
            last_ip_addresses=ip_addresses,
            last_mac_addresses=mac_addresses,
            last_registration_summary=registration_summary,
            is_active=True,
            approved_at=now if enrollment_key.auto_approve else None,
        )
        db.add(agent)
        enrollment_key.registration_count += 1
        created = True
    else:
        agent.display_name = registration.display_name or agent.display_name
        agent.hostname = registration.hostname or agent.hostname
        agent.site_name = registration.site_name or agent.site_name
        agent.agent_version = registration.agent_version or agent.agent_version
        agent.platform = registration.platform or agent.platform
        agent.platform_release = registration.platform_release or agent.platform_release
        agent.last_registration_at = now
        agent.last_ip_addresses = ip_addresses
        agent.last_mac_addresses = mac_addresses
        agent.last_registration_summary = registration_summary
        if agent.policy_id is None and enrollment_key.default_policy_id is not None:
            agent.policy_id = enrollment_key.default_policy_id
        if enrollment_key.auto_approve and agent.enrollment_state == "pending":
            agent.enrollment_state = "active"
            agent.approval_required = False
            agent.approved_at = now

    enrollment_key.last_used_at = now
    await db.flush()

    if agent.enrollment_state == "active" and not agent.api_key_hash:
        issued_api_key = _issue_agent_api_key(agent, now)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if created:
            raise HTTPException(status_code=409, detail="Agent UUID already exists")
        raise HTTPException(status_code=409, detail="Failed to persist agent registration")

    await db.refresh(agent)
    policy_map = await _load_policy_map(
        db,
        [policy_id for policy_id in [agent.policy_id, enrollment_key.default_policy_id] if policy_id],
    )
    enrollment_key_map = {enrollment_key.id: enrollment_key}
    await _attach_key_and_policy(agent, policy_map, enrollment_key_map)

    audit.log(
        action="REGISTER",
        actor=f"agent:{agent.agent_uuid}",
        resource="Agent",
        resource_id=str(agent.id),
        status="success",
        details={
            "created": created,
            "state": agent.enrollment_state,
            "enrollment_key_id": enrollment_key.id,
        },
    )

    if agent.enrollment_state == "pending":
        return AgentRegistrationResponse(
            status="pending",
            approval_required=True,
            message="Agent registered and is awaiting admin approval",
            api_key=None,
            server_time=_utcnow(),
            agent=_agent_response(agent),
            policy=AgentPolicyResponse.model_validate(policy_map[agent.policy_id]) if agent.policy_id else None,
            compatibility=_agent_compatibility(agent.agent_version),
        )

    return AgentRegistrationResponse(
        status="active",
        approval_required=False,
        message=(
            "Agent approved and API key issued"
            if issued_api_key
            else "Agent already approved"
        ),
        api_key=issued_api_key,
        server_time=_utcnow(),
        agent=_agent_response(agent),
        policy=AgentPolicyResponse.model_validate(policy_map[agent.policy_id]) if agent.policy_id else None,
        compatibility=_agent_compatibility(agent.agent_version),
    )


@router.post("/{agent_id}/approve", response_model=AgentResponse)
async def approve_agent(
    agent_id: int,
    approval: AgentApprovalRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_agent_or_404(db, agent_id)
    if agent.enrollment_state != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Only pending agents can be approved ({agent.enrollment_state})",
        )
    if approval.policy_id is not None:
        await _get_policy_or_404(db, approval.policy_id)

    agent.enrollment_state = "active"
    agent.approval_required = False
    agent.is_active = True
    agent.approved_at = _utcnow()
    agent.rejected_at = None
    if approval.policy_id is not None:
        agent.policy_id = approval.policy_id
    if approval.display_name:
        agent.display_name = approval.display_name

    await db.commit()
    await db.refresh(agent)
    policy_map = await _load_policy_map(
        db,
        [agent.policy_id] if agent.policy_id else [],
    )
    enrollment_key_map = await _load_enrollment_key_map(
        db,
        [agent.enrollment_key_id] if agent.enrollment_key_id else [],
    )
    default_policy_map = await _load_policy_map(
        db,
        [
            enrollment_key.default_policy_id
            for enrollment_key in enrollment_key_map.values()
            if enrollment_key.default_policy_id
        ],
    )
    policy_map.update(default_policy_map)
    await _attach_key_and_policy(agent, policy_map, enrollment_key_map)

    audit.log(
        action="APPROVE",
        actor="user",
        resource="Agent",
        resource_id=str(agent.id),
        status="success",
        details={"agent_uuid": agent.agent_uuid},
    )
    return _agent_response(agent)


@router.post("/{agent_id}/reject", response_model=AgentResponse)
async def reject_agent(
    agent_id: int,
    rejection: AgentRejectRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_agent_or_404(db, agent_id)
    if agent.enrollment_state != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Only pending agents can be rejected ({agent.enrollment_state})",
        )
    agent.enrollment_state = "rejected"
    agent.approval_required = True
    agent.rejected_at = _utcnow()
    if rejection.reason:
        summary = agent.last_registration_summary or {}
        summary["rejection_reason"] = rejection.reason
        agent.last_registration_summary = summary

    await db.commit()
    await db.refresh(agent)
    policy_map = await _load_policy_map(
        db,
        [agent.policy_id] if agent.policy_id else [],
    )
    enrollment_key_map = await _load_enrollment_key_map(
        db,
        [agent.enrollment_key_id] if agent.enrollment_key_id else [],
    )
    default_policy_map = await _load_policy_map(
        db,
        [
            enrollment_key.default_policy_id
            for enrollment_key in enrollment_key_map.values()
            if enrollment_key.default_policy_id
        ],
    )
    policy_map.update(default_policy_map)
    await _attach_key_and_policy(agent, policy_map, enrollment_key_map)

    audit.log(
        action="REJECT",
        actor="user",
        resource="Agent",
        resource_id=str(agent.id),
        status="success",
        details={"agent_uuid": agent.agent_uuid},
    )
    return _agent_response(agent)


@router.post("/{agent_id}/revoke", response_model=AgentResponse)
async def revoke_agent(
    agent_id: int,
    revocation: AgentRevokeRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_agent_or_404(db, agent_id)
    if agent.enrollment_state == "revoked":
        raise HTTPException(status_code=409, detail="Agent is already revoked")

    agent.enrollment_state = "revoked"
    agent.approval_required = True
    agent.is_active = False
    _clear_agent_api_key(agent)
    if revocation.reason:
        summary = agent.last_registration_summary or {}
        summary["revocation_reason"] = revocation.reason
        agent.last_registration_summary = summary

    await db.commit()
    await db.refresh(agent)
    policy_map = await _load_policy_map(
        db,
        [agent.policy_id] if agent.policy_id else [],
    )
    enrollment_key_map = await _load_enrollment_key_map(
        db,
        [agent.enrollment_key_id] if agent.enrollment_key_id else [],
    )
    default_policy_map = await _load_policy_map(
        db,
        [
            enrollment_key.default_policy_id
            for enrollment_key in enrollment_key_map.values()
            if enrollment_key.default_policy_id
        ],
    )
    policy_map.update(default_policy_map)
    await _attach_key_and_policy(agent, policy_map, enrollment_key_map)

    audit.log(
        action="REVOKE",
        actor="user",
        resource="Agent",
        resource_id=str(agent.id),
        status="success",
        details={"agent_uuid": agent.agent_uuid, "reason": revocation.reason},
    )
    return _agent_response(agent)


@router.post("/{agent_id}/reactivate", response_model=AgentResponse)
async def reactivate_agent(
    agent_id: int,
    reactivation: AgentReactivateRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_agent_or_404(db, agent_id)
    if agent.enrollment_state == "active" and agent.is_active:
        raise HTTPException(status_code=409, detail="Active agents do not need reactivation")
    if agent.enrollment_state == "pending" and agent.is_active:
        raise HTTPException(status_code=409, detail="Agent is already pending approval")

    agent.enrollment_state = "pending"
    agent.approval_required = True
    agent.is_active = True
    agent.approved_at = None
    agent.rejected_at = None
    _clear_agent_api_key(agent)
    if reactivation.reason:
        summary = agent.last_registration_summary or {}
        summary["reactivation_reason"] = reactivation.reason
        agent.last_registration_summary = summary

    await db.commit()
    await db.refresh(agent)
    policy_map = await _load_policy_map(
        db,
        [agent.policy_id] if agent.policy_id else [],
    )
    enrollment_key_map = await _load_enrollment_key_map(
        db,
        [agent.enrollment_key_id] if agent.enrollment_key_id else [],
    )
    default_policy_map = await _load_policy_map(
        db,
        [
            enrollment_key.default_policy_id
            for enrollment_key in enrollment_key_map.values()
            if enrollment_key.default_policy_id
        ],
    )
    policy_map.update(default_policy_map)
    await _attach_key_and_policy(agent, policy_map, enrollment_key_map)

    audit.log(
        action="REACTIVATE",
        actor="user",
        resource="Agent",
        resource_id=str(agent.id),
        status="success",
        details={"agent_uuid": agent.agent_uuid, "reason": reactivation.reason},
    )
    return _agent_response(agent)


@router.post("/{agent_id}/rotate-api-key", response_model=AgentApiKeyRotateResponse)
async def rotate_agent_api_key(
    agent_id: int,
    rotation: AgentApiKeyRotateRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_agent_or_404(db, agent_id)

    if not agent.is_active:
        raise HTTPException(status_code=409, detail="Inactive agents cannot receive API keys")
    if agent.enrollment_state != "active":
        raise HTTPException(
            status_code=409,
            detail=f"Only active agents can rotate API keys ({agent.enrollment_state})",
        )

    previous_prefix = agent.api_key_prefix
    rotated_api_key = _issue_agent_api_key(agent, _utcnow())

    await db.commit()
    await db.refresh(agent)
    policy_map = await _load_policy_map(
        db,
        [agent.policy_id] if agent.policy_id else [],
    )
    enrollment_key_map = await _load_enrollment_key_map(
        db,
        [agent.enrollment_key_id] if agent.enrollment_key_id else [],
    )
    default_policy_map = await _load_policy_map(
        db,
        [
            enrollment_key.default_policy_id
            for enrollment_key in enrollment_key_map.values()
            if enrollment_key.default_policy_id
        ],
    )
    policy_map.update(default_policy_map)
    await _attach_key_and_policy(agent, policy_map, enrollment_key_map)

    audit.log(
        action="ROTATE_API_KEY",
        actor="user",
        resource="Agent",
        resource_id=str(agent.id),
        status="success",
        details={
            "agent_uuid": agent.agent_uuid,
            "previous_api_key_prefix": previous_prefix,
            "reason": rotation.reason,
        },
    )

    return AgentApiKeyRotateResponse(
        api_key=rotated_api_key,
        server_time=_utcnow(),
        message="Agent API key rotated; update the deployed host with the new key",
        agent=_agent_response(agent),
    )


@router.post("/{agent_id}/request-collection", response_model=AgentResponse)
async def request_agent_collection(
    agent_id: int,
    collection_request: AgentCollectionRequestCreate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_agent_or_404(db, agent_id)
    if not agent.is_active or agent.enrollment_state != "active":
        raise HTTPException(
            status_code=409,
            detail=f"Only active agents can receive collection requests ({agent.enrollment_state})",
        )
    if not agent.api_key_hash:
        raise HTTPException(
            status_code=409,
            detail="Agent does not have an API key yet; approve and let it register first",
        )

    now = _utcnow()
    agent.collection_requested_at = now
    agent.collection_request_reason = collection_request.reason
    agent.collection_request_options = {
        "passive_capture": collection_request.passive_capture.model_dump(mode="json")
    } if collection_request.passive_capture else None
    agent.collection_request_fulfilled_at = None

    await db.commit()
    await db.refresh(agent)
    policy_map = await _load_policy_map(
        db,
        [agent.policy_id] if agent.policy_id else [],
    )
    enrollment_key_map = await _load_enrollment_key_map(
        db,
        [agent.enrollment_key_id] if agent.enrollment_key_id else [],
    )
    default_policy_map = await _load_policy_map(
        db,
        [
            enrollment_key.default_policy_id
            for enrollment_key in enrollment_key_map.values()
            if enrollment_key.default_policy_id
        ],
    )
    policy_map.update(default_policy_map)
    await _attach_key_and_policy(agent, policy_map, enrollment_key_map)

    audit.log(
        action="REQUEST_COLLECTION",
        actor="user",
        resource="Agent",
        resource_id=str(agent.id),
        status="success",
        details={"agent_uuid": agent.agent_uuid, "reason": collection_request.reason},
    )
    return _agent_response(agent)


@router.get("/{agent_id}/checkins", response_model=PaginatedResponse)
async def list_agent_checkins(
    agent_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await _get_agent_or_404(db, agent_id)

    total = (
        await db.execute(
            select(func.count(AgentCheckIn.id)).where(AgentCheckIn.agent_id == agent_id)
        )
    ).scalar_one()
    result = await db.execute(
        select(AgentCheckIn)
        .where(AgentCheckIn.agent_id == agent_id)
        .order_by(AgentCheckIn.received_at.desc())
        .offset(skip)
        .limit(limit)
    )
    checkins = result.scalars().all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [
            AgentCheckInRecordResponse.model_validate(checkin) for checkin in checkins
        ],
    }


@router.get("/{agent_id}/observations", response_model=PaginatedResponse)
async def list_agent_observations(
    agent_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    observation_type: Optional[str] = Query(None),
    observation_role: Optional[str] = Query(None),
    min_confidence: Optional[int] = Query(None, ge=0, le=100),
    is_current: Optional[bool] = Query(None),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await _get_agent_or_404(db, agent_id)

    query = select(AgentObservation).where(AgentObservation.agent_id == agent_id)
    count_query = select(func.count(AgentObservation.id)).where(
        AgentObservation.agent_id == agent_id
    )
    if observation_type:
        query = query.where(AgentObservation.observation_type == observation_type)
        count_query = count_query.where(
            AgentObservation.observation_type == observation_type
        )
    if observation_role:
        query = query.where(AgentObservation.observation_role == observation_role)
        count_query = count_query.where(
            AgentObservation.observation_role == observation_role
        )
    if min_confidence is not None:
        query = query.where(AgentObservation.confidence >= min_confidence)
        count_query = count_query.where(AgentObservation.confidence >= min_confidence)
    if is_current is not None:
        query = query.where(AgentObservation.is_current == is_current)
        count_query = count_query.where(AgentObservation.is_current == is_current)

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(
            AgentObservation.is_current.desc(),
            AgentObservation.last_seen_at.desc(),
            AgentObservation.id.desc(),
        )
        .offset(skip)
        .limit(limit)
    )
    observations = result.scalars().all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [
            AgentObservationResponse.model_validate(observation)
            for observation in observations
        ],
    }


@router.post("/poll", response_model=AgentPollResponse)
async def poll_agent_control(
    poll: AgentPollRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    raw_api_key = request.headers.get(settings.AGENT_API_KEY_HEADER)
    if not raw_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing agent API key",
        )

    agent = await _lookup_agent_by_api_key(db, raw_api_key)
    if poll.agent_uuid != agent.agent_uuid:
        raise HTTPException(
            status_code=409,
            detail="Payload agent_uuid does not match the authenticated agent",
        )

    policy = None
    if agent.policy_id:
        result = await db.execute(select(AgentPolicy).where(AgentPolicy.id == agent.policy_id))
        policy = result.scalar_one_or_none()

    policy_map = await _load_policy_map(
        db,
        [agent.policy_id] if agent.policy_id else [],
    )
    enrollment_key_map = await _load_enrollment_key_map(
        db,
        [agent.enrollment_key_id] if agent.enrollment_key_id else [],
    )
    default_policy_map = await _load_policy_map(
        db,
        [
            enrollment_key.default_policy_id
            for enrollment_key in enrollment_key_map.values()
            if enrollment_key.default_policy_id
        ],
    )
    policy_map.update(default_policy_map)
    await _attach_key_and_policy(agent, policy_map, enrollment_key_map)

    return AgentPollResponse(
        server_time=_utcnow(),
        agent=_agent_response(agent),
        policy=AgentPolicyResponse.model_validate(policy) if policy else None,
        compatibility=_agent_compatibility(agent.agent_version),
        collection_request=_pending_collection_request(agent),
    )


@router.post("/check-in", response_model=AgentCheckInResponse)
async def agent_check_in(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    raw_api_key = request.headers.get(settings.AGENT_API_KEY_HEADER)
    if not raw_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing agent API key",
        )

    agent = await _lookup_agent_by_api_key(db, raw_api_key)

    raw_body = await request.body()
    if len(raw_body) > settings.AGENT_MAX_REPORT_BYTES:
        raise HTTPException(status_code=413, detail="Compressed report exceeds server limit")

    decoded_body = _decode_request_body(raw_body, request.headers.get("content-encoding"))

    policy = None
    if agent.policy_id:
        result = await db.execute(select(AgentPolicy).where(AgentPolicy.id == agent.policy_id))
        policy = result.scalar_one_or_none()

    max_report_bytes = policy.max_report_bytes if policy else settings.AGENT_MAX_REPORT_BYTES
    if len(decoded_body) > max_report_bytes:
        raise HTTPException(status_code=413, detail="Decoded report exceeds policy size limit")

    try:
        payload = AgentCheckInRequest.model_validate_json(decoded_body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors())

    if payload.agent_uuid != agent.agent_uuid:
        raise HTTPException(
            status_code=409,
            detail="Payload agent_uuid does not match the authenticated agent",
        )

    _raise_policy_violations(agent, policy, payload)

    checkin, raw_import, policy_response, summary = await _ingest_agent_payload(
        db=db,
        agent=agent,
        payload=payload,
        decoded_body=decoded_body,
        content_encoding=request.headers.get("content-encoding"),
        source_ip=request.client.host if request.client else None,
        policy=policy,
    )
    await db.commit()
    await db.refresh(agent)
    await db.refresh(checkin)
    await db.refresh(raw_import)
    policy_map = await _load_policy_map(
        db,
        [agent.policy_id] if agent.policy_id else [],
    )
    enrollment_key_map = await _load_enrollment_key_map(
        db,
        [agent.enrollment_key_id] if agent.enrollment_key_id else [],
    )
    default_policy_map = await _load_policy_map(
        db,
        [
            enrollment_key.default_policy_id
            for enrollment_key in enrollment_key_map.values()
            if enrollment_key.default_policy_id
        ],
    )
    policy_map.update(default_policy_map)
    await _attach_key_and_policy(agent, policy_map, enrollment_key_map)

    audit.log(
        action="CHECKIN",
        actor=f"agent:{agent.agent_uuid}",
        resource="Agent",
        resource_id=str(agent.id),
        status="success",
        details={
            "raw_import_id": raw_import.id,
            "records_created": checkin.records_created,
            "observations_created": summary.get("observations_created"),
            "observations_refreshed": summary.get("observations_refreshed"),
            "observations_reactivated": summary.get("observations_reactivated"),
            "observations_stale": summary.get("observations_stale"),
            "observations_removed": summary.get("observations_removed"),
            "evidence_created": summary.get("evidence_created"),
            "evidence_refreshed": summary.get("evidence_refreshed"),
        },
    )

    return AgentCheckInResponse(
        status="accepted",
        server_time=_utcnow(),
        agent=_agent_response(agent),
        policy=policy_response,
        compatibility=_agent_compatibility(agent.agent_version),
        checkin=AgentCheckInRecordResponse.model_validate(checkin),
        summary=summary,
    )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: int,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_agent_or_404(db, agent_id)
    policy_map = await _load_policy_map(
        db,
        [agent.policy_id] if agent.policy_id else [],
    )
    enrollment_key_map = await _load_enrollment_key_map(
        db,
        [agent.enrollment_key_id] if agent.enrollment_key_id else [],
    )
    default_policy_map = await _load_policy_map(
        db,
        [
            enrollment_key.default_policy_id
            for enrollment_key in enrollment_key_map.values()
            if enrollment_key.default_policy_id
        ],
    )
    policy_map.update(default_policy_map)
    await _attach_key_and_policy(agent, policy_map, enrollment_key_map)
    return _agent_response(agent)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: int,
    agent_update: AgentUpdate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_agent_or_404(db, agent_id)
    update_data = agent_update.model_dump(exclude_unset=True)

    if "policy_id" in update_data and update_data["policy_id"] is not None:
        await _get_policy_or_404(db, update_data["policy_id"])
    if "enrollment_key_id" in update_data and update_data["enrollment_key_id"] is not None:
        await _get_enrollment_key_or_404(db, update_data["enrollment_key_id"])

    for field, value in update_data.items():
        setattr(agent, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Agent UUID already exists")

    await db.refresh(agent)
    policy_map = await _load_policy_map(
        db,
        [agent.policy_id] if agent.policy_id else [],
    )
    enrollment_key_map = await _load_enrollment_key_map(
        db,
        [agent.enrollment_key_id] if agent.enrollment_key_id else [],
    )
    default_policy_map = await _load_policy_map(
        db,
        [
            enrollment_key.default_policy_id
            for enrollment_key in enrollment_key_map.values()
            if enrollment_key.default_policy_id
        ],
    )
    policy_map.update(default_policy_map)
    await _attach_key_and_policy(agent, policy_map, enrollment_key_map)

    audit.log(
        action="UPDATE",
        actor="user",
        resource="Agent",
        resource_id=str(agent.id),
        status="success",
        details={"agent_uuid": agent.agent_uuid},
    )
    return _agent_response(agent)
    AgentObservationResponse,

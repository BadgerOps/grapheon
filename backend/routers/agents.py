import gzip
import hashlib
import logging
import secrets
from datetime import datetime, timezone
from ipaddress import ip_address as parse_ip
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_admin, require_any_authenticated
from config import settings
from database import get_db
from models import (
    ARPEntry,
    Agent,
    AgentCheckIn,
    AgentEnrollmentKey,
    AgentPolicy,
    Connection,
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
    AgentCreate,
    AgentEnrollmentKeyCreate,
    AgentEnrollmentKeyCreateResponse,
    AgentEnrollmentKeyResponse,
    AgentEnrollmentKeyUpdate,
    AgentPolicyCreate,
    AgentPolicyResponse,
    AgentPolicyUpdate,
    AgentRegistrationRequest,
    AgentRegistrationResponse,
    AgentRejectRequest,
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])

AGENT_SOURCE_TYPE = "agent"
AGENT_IMPORT_TYPE = "agent"
ENROLLMENT_KEY_PREFIX = "gaek"
AGENT_API_KEY_PREFIX = "gpak"


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
        if hostname:
            host.hostname = hostname
        if mac_address and not host.mac_address:
            host.mac_address = mac_address
        current_sources = host.source_types or []
        if AGENT_SOURCE_TYPE not in current_sources:
            host.source_types = current_sources + [AGENT_SOURCE_TYPE]
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
) -> bool:
    if not mac_address:
        return False

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
        return False

    arp_entry = ARPEntry(
        ip_address=ip_address,
        mac_address=mac_address,
        interface=interface,
        entry_type=state_value,
        source_type=AGENT_SOURCE_TYPE,
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
    return True


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
) -> bool:
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
        return False

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
    return True


async def _ingest_agent_payload(
    db: AsyncSession,
    agent: Agent,
    payload: AgentCheckInRequest,
    decoded_body: bytes,
    content_encoding: Optional[str],
    source_ip: Optional[str],
) -> tuple[AgentCheckIn, RawImport, AgentPolicyResponse | None, dict]:
    now = _utcnow()
    host_creates = 0
    arp_creates = 0
    connection_creates = 0

    seen_ips: set[str] = set()
    seen_macs: set[str] = set()

    for address in payload.addresses:
        _, created = await _upsert_host(
            db,
            address.ip_address,
            hostname=payload.hostname,
            mac_address=address.mac_address,
        )
        host_creates += int(created)
        seen_ips.add(address.ip_address)
        if address.mac_address:
            seen_macs.add(address.mac_address)

    for neighbor in payload.neighbors:
        _, created = await _upsert_host(
            db,
            neighbor.ip_address,
            hostname=neighbor.hostname,
            mac_address=neighbor.mac_address,
        )
        host_creates += int(created)
        arp_created = await _upsert_arp_entry(
            db,
            neighbor.ip_address,
            neighbor.mac_address,
            neighbor.interface,
            neighbor.state,
        )
        arp_creates += int(arp_created)
        seen_ips.add(neighbor.ip_address)
        if neighbor.mac_address:
            seen_macs.add(neighbor.mac_address)

    for route in payload.routes:
        if route.source_ip:
            _, created = await _upsert_host(
                db,
                route.source_ip,
                hostname=payload.hostname,
            )
            host_creates += int(created)
            seen_ips.add(route.source_ip)
        if route.gateway:
            _, created = await _upsert_host(db, route.gateway)
            host_creates += int(created)
            seen_ips.add(route.gateway)

    for connection in payload.connections:
        _, created = await _upsert_host(
            db,
            connection.local_ip,
            hostname=payload.hostname,
        )
        host_creates += int(created)
        seen_ips.add(connection.local_ip)
        if not parse_ip(connection.remote_ip).is_unspecified:
            _, remote_created = await _upsert_host(db, connection.remote_ip)
            host_creates += int(remote_created)
            seen_ips.add(connection.remote_ip)
        connection_created = await _upsert_connection(
            db,
            local_ip=connection.local_ip,
            local_port=connection.local_port,
            remote_ip=connection.remote_ip,
            remote_port=connection.remote_port,
            protocol=connection.protocol,
            state_value=connection.state,
            pid=connection.pid,
            process_name=connection.process_name,
        )
        connection_creates += int(connection_created)

    raw_import = RawImport(
        source_type=AGENT_SOURCE_TYPE,
        import_type=AGENT_IMPORT_TYPE,
        filename=f"{agent.agent_uuid}-{payload.observed_at.isoformat()}.json",
        source_host=_source_host_from_payload(payload),
        raw_data=decoded_body.decode("utf-8"),
        tags=["agent", f"agent_uuid:{agent.agent_uuid}"],
        notes="Passive agent check-in",
        parse_status="success",
        parsed_count=host_creates + arp_creates + connection_creates,
        parse_results={
            "observed_at": payload.observed_at.isoformat(),
            "sequence_number": payload.sequence_number,
            "full_snapshot": payload.full_snapshot,
            "counts": {
                "hosts_created": host_creates,
                "arp_entries_created": arp_creates,
                "connections_created": connection_creates,
                "addresses_seen": len(payload.addresses),
                "neighbors_seen": len(payload.neighbors),
                "routes_seen": len(payload.routes),
            },
            "content_encoding": content_encoding or "identity",
            "auth_method": "api_key",
        },
        created_at=now,
        processed_at=now,
    )
    db.add(raw_import)
    await db.flush()

    summary = {
        "hosts_created": host_creates,
        "arp_entries_created": arp_creates,
        "connections_created": connection_creates,
        "ip_addresses_seen": sorted(seen_ips),
        "mac_addresses_seen": sorted(seen_macs),
        "neighbor_count": len(payload.neighbors),
        "connection_count": len(payload.connections),
        "route_count": len(payload.routes),
        "raw_import_id": raw_import.id,
    }

    checkin = AgentCheckIn(
        agent_id=agent.id,
        raw_import_id=raw_import.id,
        observed_at=payload.observed_at,
        received_at=now,
        sequence_number=payload.sequence_number,
        full_snapshot=payload.full_snapshot,
        content_encoding=content_encoding or "identity",
        source_ip=source_ip,
        auth_method="api_key",
        api_key_prefix=agent.api_key_prefix,
        report=payload.model_dump(mode="json"),
        summary=summary,
        status="accepted",
        records_created=host_creates + arp_creates + connection_creates,
    )
    db.add(checkin)

    agent.hostname = payload.hostname or agent.hostname
    agent.agent_version = payload.agent_version or agent.agent_version
    agent.platform = payload.platform or agent.platform
    agent.platform_release = payload.platform_release or agent.platform_release
    agent.last_ip_addresses = sorted(seen_ips)
    agent.last_mac_addresses = sorted(seen_macs)
    agent.last_checkin_summary = summary
    agent.last_seen_at = now

    await db.flush()

    policy = None
    if agent.policy_id:
        result = await db.execute(select(AgentPolicy).where(AgentPolicy.id == agent.policy_id))
        policy = result.scalar_one_or_none()

    return (
        checkin,
        raw_import,
        AgentPolicyResponse.model_validate(policy) if policy else None,
        summary,
    )


def _agent_response(agent: Agent) -> AgentResponse:
    return AgentResponse.model_validate(agent)


@router.get("/policies", response_model=PaginatedResponse)
async def list_policies(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    is_active: Optional[bool] = Query(None),
    user: User = Depends(require_any_authenticated),
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
    user: User = Depends(require_any_authenticated),
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
    )


@router.post("/{agent_id}/approve", response_model=AgentResponse)
async def approve_agent(
    agent_id: int,
    approval: AgentApprovalRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    agent = await _get_agent_or_404(db, agent_id)
    if approval.policy_id is not None:
        await _get_policy_or_404(db, approval.policy_id)

    agent.enrollment_state = "active"
    agent.approval_required = False
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


@router.get("/{agent_id}/checkins", response_model=PaginatedResponse)
async def list_agent_checkins(
    agent_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    user: User = Depends(require_any_authenticated),
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

    checkin, raw_import, policy_response, summary = await _ingest_agent_payload(
        db=db,
        agent=agent,
        payload=payload,
        decoded_body=decoded_body,
        content_encoding=request.headers.get("content-encoding"),
        source_ip=request.client.host if request.client else None,
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
        },
    )

    return AgentCheckInResponse(
        status="accepted",
        server_time=_utcnow(),
        agent=_agent_response(agent),
        policy=policy_response,
        checkin=AgentCheckInRecordResponse.model_validate(checkin),
        summary=summary,
    )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: int,
    user: User = Depends(require_any_authenticated),
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

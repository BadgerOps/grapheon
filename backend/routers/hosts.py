from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime

from database import get_db
from models import Host, Port, User
from auth.dependencies import require_any_authenticated, require_editor
from schemas import (
    HostCreate,
    HostUpdate,
    HostResponse,
    PortResponse,
    PaginatedResponse,
)
from utils.audit import audit

router = APIRouter(prefix="/api/hosts", tags=["hosts"])


@router.get("", response_model=PaginatedResponse)
async def list_hosts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    is_active: bool = Query(True),
    user: User = Depends(require_any_authenticated),
    db: AsyncSession = Depends(get_db),
):
    """
    List all hosts with pagination and filtering.

    Query parameters:
    - skip: Number of hosts to skip (default 0)
    - limit: Number of hosts to return (default 50, max 1000)
    - is_active: Filter by active status (default True)
    """
    # Get total count
    count_result = await db.execute(
        select(func.count(Host.id)).where(Host.is_active == is_active)
    )
    total = count_result.scalar()

    # Get paginated results
    result = await db.execute(
        select(Host)
        .where(Host.is_active == is_active)
        .offset(skip)
        .limit(limit)
        .order_by(Host.last_seen.desc())
    )
    hosts = result.scalars().all()

    # Count open ports per host for dashboard summaries
    if hosts:
        host_ids = [host.id for host in hosts]
        ports_result = await db.execute(
            select(Port.host_id, func.count(Port.id))
            .where(Port.host_id.in_(host_ids), Port.state == "open")
            .group_by(Port.host_id)
        )
        ports_count_map = {row[0]: row[1] for row in ports_result.all()}
        for host in hosts:
            setattr(host, "ports_count", ports_count_map.get(host.id, 0))

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [HostResponse.model_validate(host) for host in hosts],
    }


@router.get("/{host_id}", response_model=dict)
async def get_host(host_id: int, user: User = Depends(require_any_authenticated), db: AsyncSession = Depends(get_db)):
    """
    Get a single host by ID with its associated ports.
    """
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()

    if not host:
        raise HTTPException(status_code=404, detail="Host not found")

    # Get ports for this host
    ports_result = await db.execute(select(Port).where(Port.host_id == host_id))
    ports = ports_result.scalars().all()

    host_data = HostResponse.model_validate(host)
    ports_data = [PortResponse.model_validate(port) for port in ports]

    return {
        "host": host_data,
        "ports": ports_data,
    }


@router.post("", response_model=HostResponse, status_code=201)
async def create_host(
    host: HostCreate,
    user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new host.
    """
    # Check if host with this IP already exists
    result = await db.execute(
        select(Host).where(Host.ip_address == host.ip_address)
    )
    existing_host = result.scalar_one_or_none()

    if existing_host:
        raise HTTPException(
            status_code=409,
            detail=f"Host with IP {host.ip_address} already exists",
        )

    # Create new host
    db_host = Host(
        ip_address=host.ip_address,
        ip_v6_address=host.ip_v6_address,
        mac_address=host.mac_address,
        hostname=host.hostname,
        fqdn=host.fqdn,
        netbios_name=host.netbios_name,
        os_name=host.os_name,
        os_version=host.os_version,
        os_family=host.os_family,
        os_confidence=host.os_confidence,
        device_type=host.device_type,
        vendor=host.vendor,
        criticality=host.criticality,
        owner=host.owner,
        location=host.location,
        tags=host.tags,
        notes=host.notes,
        is_verified=host.is_verified,
        is_active=host.is_active,
        source_types=host.source_types,
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
    )

    db.add(db_host)
    await db.commit()
    await db.refresh(db_host)

    audit.log_host_crud(operation="create", host_id=db_host.id, ip_address=db_host.ip_address, hostname=db_host.hostname)
    return HostResponse.model_validate(db_host)


@router.put("/{host_id}", response_model=HostResponse)
async def update_host(
    host_id: int,
    host_update: HostUpdate,
    user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a host by ID.
    """
    result = await db.execute(select(Host).where(Host.id == host_id))
    db_host = result.scalar_one_or_none()

    if not db_host:
        raise HTTPException(status_code=404, detail="Host not found")

    # Update only provided fields
    update_data = host_update.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(db_host, field, value)

    db_host.last_seen = datetime.utcnow()

    await db.commit()
    await db.refresh(db_host)

    audit.log_host_crud(operation="update", host_id=host_id, ip_address=db_host.ip_address, hostname=db_host.hostname)
    return HostResponse.model_validate(db_host)


@router.delete("/{host_id}", status_code=204)
async def delete_host(host_id: int, user: User = Depends(require_editor), db: AsyncSession = Depends(get_db)):
    """
    Soft delete a host by setting is_active to False.
    """
    result = await db.execute(select(Host).where(Host.id == host_id))
    db_host = result.scalar_one_or_none()

    if not db_host:
        raise HTTPException(status_code=404, detail="Host not found")

    db_host.is_active = False
    db_host.last_seen = datetime.utcnow()

    await db.commit()
    audit.log_host_crud(operation="delete", host_id=host_id, ip_address=db_host.ip_address, hostname=db_host.hostname)

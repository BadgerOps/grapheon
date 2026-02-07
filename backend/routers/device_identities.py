"""
API endpoints for device identity management.

Handles:
- CRUD operations for DeviceIdentity records
- Linking/unlinking hosts to device identities
- Querying devices by MAC or IP
"""

import logging
from datetime import datetime
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database import get_db
from models import DeviceIdentity, Host, User
from auth.dependencies import require_any_authenticated, require_editor
from schemas import (
    DeviceIdentityCreate,
    DeviceIdentityUpdate,
    LinkHostsRequest,
)
from utils.audit import audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/device-identities", tags=["device-identities"])


@router.get("", response_model=Dict)
async def list_device_identities(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    active_only: bool = Query(True),
    user: User = Depends(require_any_authenticated),
    db: AsyncSession = Depends(get_db),
):
    """
    List all device identities with pagination.

    Returns device identities with linked host counts.
    """
    try:
        query = select(DeviceIdentity)
        if active_only:
            query = query.where(DeviceIdentity.is_active.is_(True))
        query = query.order_by(DeviceIdentity.id).offset(skip).limit(limit)

        result = await db.execute(query)
        devices = result.scalars().all()

        # Count total
        count_query = select(func.count(DeviceIdentity.id))
        if active_only:
            count_query = count_query.where(DeviceIdentity.is_active.is_(True))
        total = (await db.execute(count_query)).scalar() or 0

        # Get host counts per device
        items = []
        for device in devices:
            host_count_result = await db.execute(
                select(func.count(Host.id)).where(Host.device_id == device.id)
            )
            host_count = host_count_result.scalar() or 0

            items.append({
                "id": device.id,
                "guid": device.guid,
                "name": device.name,
                "device_type": device.device_type,
                "mac_addresses": device.mac_addresses,
                "ip_addresses": device.ip_addresses,
                "notes": device.notes,
                "source": device.source,
                "is_active": device.is_active,
                "host_count": host_count,
                "first_seen": device.first_seen.isoformat() if device.first_seen else None,
                "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            })

        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "items": items,
        }
    except Exception as e:
        logger.error(f"Failed to list device identities: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{device_id}", response_model=Dict)
async def get_device_identity(
    device_id: int,
    user: User = Depends(require_any_authenticated),
    db: AsyncSession = Depends(get_db),
):
    """Get a device identity by ID, including linked hosts."""
    try:
        result = await db.execute(
            select(DeviceIdentity).where(DeviceIdentity.id == device_id)
        )
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device identity not found")

        # Get linked hosts
        host_result = await db.execute(
            select(Host).where(Host.device_id == device_id)
        )
        linked_hosts = host_result.scalars().all()

        return {
            "id": device.id,
            "guid": device.guid,
            "name": device.name,
            "device_type": device.device_type,
            "mac_addresses": device.mac_addresses,
            "ip_addresses": device.ip_addresses,
            "notes": device.notes,
            "source": device.source,
            "is_active": device.is_active,
            "first_seen": device.first_seen.isoformat() if device.first_seen else None,
            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            "linked_hosts": [
                {
                    "id": h.id,
                    "ip_address": h.ip_address,
                    "hostname": h.hostname,
                    "mac_address": h.mac_address,
                    "device_type": h.device_type,
                    "vlan_id": h.vlan_id,
                    "vlan_name": h.vlan_name,
                    "is_active": h.is_active,
                }
                for h in linked_hosts
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get device identity: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=Dict)
async def create_device_identity(
    data: DeviceIdentityCreate,
    user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    """Create a new device identity."""
    try:
        device = DeviceIdentity(
            name=data.name,
            device_type=data.device_type,
            mac_addresses=data.mac_addresses,
            ip_addresses=data.ip_addresses,
            notes=data.notes,
            source=data.source or "manual",
            is_active=data.is_active,
        )
        db.add(device)
        await db.commit()
        await db.refresh(device)

        logger.info(f"Created device identity {device.id}: {device.name}")
        audit.log_device_identity_change(operation="create", device_id=device.id, device_name=device.name)

        return {
            "success": True,
            "data": {
                "id": device.id,
                "guid": device.guid,
                "name": device.name,
                "device_type": device.device_type,
            },
            "message": f"Device identity created: {device.name or device.id}",
        }
    except Exception as e:
        logger.error(f"Failed to create device identity: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{device_id}", response_model=Dict)
async def update_device_identity(
    device_id: int,
    data: DeviceIdentityUpdate,
    user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing device identity."""
    try:
        result = await db.execute(
            select(DeviceIdentity).where(DeviceIdentity.id == device_id)
        )
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device identity not found")

        # Update only provided fields
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(device, field, value)

        device.last_seen = datetime.utcnow()
        await db.commit()
        await db.refresh(device)

        logger.info(f"Updated device identity {device_id}")

        return {
            "success": True,
            "data": {
                "id": device.id,
                "name": device.name,
                "device_type": device.device_type,
            },
            "message": f"Device identity {device_id} updated",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update device identity: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{device_id}", response_model=Dict)
async def delete_device_identity(
    device_id: int,
    user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a device identity. Unlinks all hosts (sets device_id=NULL)."""
    try:
        result = await db.execute(
            select(DeviceIdentity).where(DeviceIdentity.id == device_id)
        )
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device identity not found")

        # Unlink all hosts
        host_result = await db.execute(
            select(Host).where(Host.device_id == device_id)
        )
        linked_hosts = host_result.scalars().all()
        for host in linked_hosts:
            host.device_id = None

        device.is_active = False
        device.last_seen = datetime.utcnow()
        await db.commit()

        logger.info(
            f"Soft-deleted device identity {device_id}, unlinked {len(linked_hosts)} hosts"
        )

        return {
            "success": True,
            "message": f"Device identity {device_id} deleted, {len(linked_hosts)} hosts unlinked",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete device identity: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{device_id}/link-hosts", response_model=Dict)
async def link_hosts_to_device(
    device_id: int,
    data: LinkHostsRequest,
    user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually link hosts to a device identity.

    Sets device_id on the specified hosts. If a host is already linked
    to a different device, it will be re-linked to this one.
    """
    try:
        # Verify device exists
        result = await db.execute(
            select(DeviceIdentity).where(DeviceIdentity.id == device_id)
        )
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device identity not found")

        linked = 0
        not_found = []
        for host_id in data.host_ids:
            host_result = await db.execute(select(Host).where(Host.id == host_id))
            host = host_result.scalar_one_or_none()
            if host:
                host.device_id = device_id
                linked += 1
            else:
                not_found.append(host_id)

        # Update device's IP/MAC lists from linked hosts
        all_hosts_result = await db.execute(
            select(Host).where(Host.device_id == device_id)
        )
        all_hosts = all_hosts_result.scalars().all()
        device.ip_addresses = list(set(h.ip_address for h in all_hosts if h.ip_address))
        device.mac_addresses = list(set(h.mac_address for h in all_hosts if h.mac_address))
        device.last_seen = datetime.utcnow()

        await db.commit()

        logger.info(f"Linked {linked} hosts to device identity {device_id}")
        audit.log_device_identity_change(operation="link_hosts", device_id=device_id, host_ids=data.host_ids)

        return {
            "success": True,
            "data": {
                "device_id": device_id,
                "hosts_linked": linked,
                "hosts_not_found": not_found,
            },
            "message": f"Linked {linked} hosts to device {device.name or device_id}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to link hosts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{device_id}/unlink-host/{host_id}", response_model=Dict)
async def unlink_host_from_device(
    device_id: int,
    host_id: int,
    user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    """Unlink a specific host from a device identity."""
    try:
        host_result = await db.execute(select(Host).where(Host.id == host_id))
        host = host_result.scalar_one_or_none()
        if not host:
            raise HTTPException(status_code=404, detail="Host not found")

        if host.device_id != device_id:
            raise HTTPException(
                status_code=400,
                detail=f"Host {host_id} is not linked to device {device_id}",
            )

        host.device_id = None
        await db.commit()

        logger.info(f"Unlinked host {host_id} from device identity {device_id}")
        audit.log_device_identity_change(operation="unlink_host", device_id=device_id)

        return {
            "success": True,
            "message": f"Host {host_id} unlinked from device {device_id}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unlink host: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

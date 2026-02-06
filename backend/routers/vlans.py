"""
VLAN configuration management endpoints.

Provides CRUD operations for VLAN configs that map subnet CIDRs
to VLAN IDs for network topology visualization grouping.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database import get_db
from models import VLANConfig, Host

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vlans", tags=["vlans"])

# Default VLAN color palette
VLAN_COLORS = [
    "#3b82f6",  # Blue
    "#22c55e",  # Green
    "#f97316",  # Orange
    "#8b5cf6",  # Purple
    "#ec4899",  # Pink
    "#06b6d4",  # Cyan
    "#eab308",  # Yellow
    "#ef4444",  # Red
    "#14b8a6",  # Teal
    "#f43f5e",  # Rose
]


@router.get("")
async def list_vlans(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """List all configured VLANs with host counts."""
    result = await db.execute(select(VLANConfig).order_by(VLANConfig.vlan_id))
    vlans = result.scalars().all()

    vlan_list = []
    for vlan in vlans:
        # Count hosts assigned to this VLAN
        host_count_result = await db.execute(
            select(func.count(Host.id)).where(Host.vlan_id == vlan.vlan_id)
        )
        host_count = host_count_result.scalar() or 0

        vlan_list.append({
            "id": vlan.id,
            "vlan_id": vlan.vlan_id,
            "vlan_name": vlan.vlan_name,
            "description": vlan.description,
            "subnet_cidrs": vlan.subnet_cidrs or [],
            "color": vlan.color,
            "is_management": vlan.is_management,
            "host_count": host_count,
            "created_at": vlan.created_at.isoformat() if vlan.created_at else None,
            "updated_at": vlan.updated_at.isoformat() if vlan.updated_at else None,
        })

    return {
        "vlans": vlan_list,
        "total": len(vlan_list),
    }


@router.get("/{vlan_id}")
async def get_vlan(
    vlan_id: int,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get a specific VLAN configuration."""
    result = await db.execute(
        select(VLANConfig).where(VLANConfig.vlan_id == vlan_id)
    )
    vlan = result.scalars().first()

    if not vlan:
        raise HTTPException(status_code=404, detail=f"VLAN {vlan_id} not found")

    # Get hosts in this VLAN
    host_result = await db.execute(
        select(Host).where(Host.vlan_id == vlan_id)
    )
    hosts = host_result.scalars().all()

    return {
        "vlan_id": vlan.vlan_id,
        "vlan_name": vlan.vlan_name,
        "description": vlan.description,
        "subnet_cidrs": vlan.subnet_cidrs or [],
        "color": vlan.color,
        "is_management": vlan.is_management,
        "host_count": len(hosts),
        "hosts": [
            {"id": h.id, "ip_address": h.ip_address, "hostname": h.hostname, "device_type": h.device_type}
            for h in hosts
        ],
        "created_at": vlan.created_at.isoformat() if vlan.created_at else None,
        "updated_at": vlan.updated_at.isoformat() if vlan.updated_at else None,
    }


@router.post("")
async def create_vlan(
    vlan_id: int = Query(..., ge=0, le=4094, description="802.1Q VLAN ID"),
    vlan_name: str = Query(..., description="Human-readable VLAN name"),
    description: Optional[str] = Query(None, description="VLAN description"),
    subnet_cidrs: Optional[str] = Query(None, description="Comma-separated CIDR list, e.g. '192.168.10.0/24,10.0.0.0/8'"),
    color: Optional[str] = Query(None, description="Hex color for visualization, e.g. '#3b82f6'"),
    is_management: bool = Query(False, description="Management VLAN flag"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Create a new VLAN configuration."""
    # Check for duplicate
    existing = await db.execute(
        select(VLANConfig).where(VLANConfig.vlan_id == vlan_id)
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail=f"VLAN {vlan_id} already exists")

    # Parse subnet CIDRs
    cidrs = [s.strip() for s in subnet_cidrs.split(",")] if subnet_cidrs else []

    # Auto-assign color if not provided
    if not color:
        color = VLAN_COLORS[vlan_id % len(VLAN_COLORS)]

    vlan = VLANConfig(
        vlan_id=vlan_id,
        vlan_name=vlan_name,
        description=description,
        subnet_cidrs=cidrs,
        color=color,
        is_management=is_management,
    )
    db.add(vlan)
    await db.commit()
    await db.refresh(vlan)

    logger.info(f"Created VLAN {vlan_id} ({vlan_name}) with subnets: {cidrs}")

    return {
        "status": "created",
        "vlan_id": vlan.vlan_id,
        "vlan_name": vlan.vlan_name,
        "subnet_cidrs": vlan.subnet_cidrs,
        "color": vlan.color,
    }


@router.put("/{vlan_id}")
async def update_vlan(
    vlan_id: int,
    vlan_name: Optional[str] = Query(None),
    description: Optional[str] = Query(None),
    subnet_cidrs: Optional[str] = Query(None, description="Comma-separated CIDR list"),
    color: Optional[str] = Query(None),
    is_management: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Update an existing VLAN configuration."""
    result = await db.execute(
        select(VLANConfig).where(VLANConfig.vlan_id == vlan_id)
    )
    vlan = result.scalars().first()

    if not vlan:
        raise HTTPException(status_code=404, detail=f"VLAN {vlan_id} not found")

    if vlan_name is not None:
        vlan.vlan_name = vlan_name
    if description is not None:
        vlan.description = description
    if subnet_cidrs is not None:
        vlan.subnet_cidrs = [s.strip() for s in subnet_cidrs.split(",")]
    if color is not None:
        vlan.color = color
    if is_management is not None:
        vlan.is_management = is_management

    vlan.updated_at = datetime.utcnow()
    await db.commit()

    logger.info(f"Updated VLAN {vlan_id}")

    return {
        "status": "updated",
        "vlan_id": vlan.vlan_id,
        "vlan_name": vlan.vlan_name,
        "subnet_cidrs": vlan.subnet_cidrs,
        "color": vlan.color,
    }


@router.delete("/{vlan_id}")
async def delete_vlan(
    vlan_id: int,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Delete a VLAN configuration."""
    result = await db.execute(
        select(VLANConfig).where(VLANConfig.vlan_id == vlan_id)
    )
    vlan = result.scalars().first()

    if not vlan:
        raise HTTPException(status_code=404, detail=f"VLAN {vlan_id} not found")

    # Clear vlan_id from hosts that referenced this VLAN
    host_result = await db.execute(
        select(Host).where(Host.vlan_id == vlan_id)
    )
    hosts = host_result.scalars().all()
    for host in hosts:
        host.vlan_id = None
        host.vlan_name = None

    await db.delete(vlan)
    await db.commit()

    logger.info(f"Deleted VLAN {vlan_id}, cleared {len(hosts)} host assignments")

    return {
        "status": "deleted",
        "vlan_id": vlan_id,
        "hosts_cleared": len(hosts),
    }


@router.post("/auto-assign")
async def auto_assign_vlans(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Auto-assign hosts to VLANs based on subnet CIDR matching.

    For each VLANConfig, checks all active hosts and assigns those
    whose IP falls within any of the VLAN's configured subnet CIDRs.
    """
    from ipaddress import ip_address, ip_network

    # Fetch all VLAN configs
    vlan_result = await db.execute(select(VLANConfig))
    vlans = vlan_result.scalars().all()

    if not vlans:
        return {"status": "no_vlans_configured", "assigned": 0}

    # Build VLAN → network list mapping
    vlan_networks = {}
    for vlan in vlans:
        networks = []
        for cidr in (vlan.subnet_cidrs or []):
            try:
                networks.append(ip_network(cidr, strict=False))
            except ValueError:
                logger.warning(f"Invalid CIDR '{cidr}' in VLAN {vlan.vlan_id}")
        vlan_networks[vlan.vlan_id] = (vlan, networks)

    # Fetch all active hosts
    host_result = await db.execute(select(Host).where(Host.is_active.is_(True)))
    hosts = host_result.scalars().all()

    assigned_count = 0
    for host in hosts:
        if not host.ip_address:
            continue
        try:
            addr = ip_address(host.ip_address)
        except ValueError:
            continue

        # Check each VLAN's subnets
        for vid, (vlan, networks) in vlan_networks.items():
            for net in networks:
                if addr in net:
                    if host.vlan_id != vid:
                        host.vlan_id = vid
                        host.vlan_name = vlan.vlan_name
                        assigned_count += 1
                    break
            else:
                continue
            break

    await db.commit()

    logger.info(f"Auto-assigned {assigned_count} hosts to VLANs")

    return {
        "status": "completed",
        "assigned": assigned_count,
        "total_hosts": len(hosts),
        "total_vlans": len(vlans),
    }

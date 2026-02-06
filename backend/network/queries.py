"""
Database query helpers for network map generation.
"""
import logging
from collections import defaultdict
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from models import Host, Port, Connection, RouteHop, ARPEntry, VLANConfig, DeviceIdentity

logger = logging.getLogger(__name__)


async def fetch_hosts(
    db: AsyncSession,
    vlan_filter: Optional[int] = None,
    include_inactive: bool = False,
) -> list:
    """Fetch hosts with optional filters."""
    query = select(Host)
    if not include_inactive:
        query = query.where(Host.is_active.is_(True))
    if vlan_filter is not None:
        query = query.where(Host.vlan_id == vlan_filter)
    result = await db.execute(query)
    return result.scalars().all()


async def fetch_vlan_configs(db: AsyncSession) -> dict:
    """Fetch all VLAN configs, keyed by vlan_id."""
    result = await db.execute(select(VLANConfig).order_by(VLANConfig.vlan_id))
    return {v.vlan_id: v for v in result.scalars().all()}


async def fetch_arp_segments(db: AsyncSession) -> dict:
    """Fetch ARP entries and build IP → interface segment mapping."""
    ip_to_segment = {}
    result = await db.execute(select(ARPEntry))
    for arp_entry in result.scalars().all():
        if arp_entry.interface:
            ip_to_segment[arp_entry.ip_address] = arp_entry.interface
    return ip_to_segment


async def fetch_connections(db: AsyncSession) -> list:
    """Fetch all connection records."""
    result = await db.execute(select(Connection))
    return result.scalars().all()


async def fetch_port_counts(db: AsyncSession, host_ids: list[int]) -> dict[int, int]:
    """
    Batch-fetch open port counts for all hosts in a single query.

    Returns dict of host_id → open_port_count.
    Replaces N+1 per-host queries with one GROUP BY query.
    """
    if not host_ids:
        return {}

    result = await db.execute(
        select(Port.host_id, func.count(Port.id))
        .where(and_(Port.host_id.in_(host_ids), Port.state == "open"))
        .group_by(Port.host_id)
    )
    return dict(result.all())


async def fetch_device_identities(db: AsyncSession) -> dict:
    """Fetch all active DeviceIdentity records, keyed by id."""
    result = await db.execute(
        select(DeviceIdentity).where(DeviceIdentity.is_active.is_(True))
    )
    return {di.id: di for di in result.scalars().all()}


async def fetch_route_hops(
    db: AsyncSession,
    destination: Optional[str] = None,
) -> list:
    """Fetch route hops with optional destination filter."""
    query = select(RouteHop)
    if destination:
        query = query.where(RouteHop.dest_ip == destination)
    result = await db.execute(query.order_by(RouteHop.trace_id, RouteHop.hop_number))
    return result.scalars().all()


def build_device_id_to_hosts(hosts: list) -> dict:
    """Group hosts by device_id for shared gateway detection."""
    device_id_to_hosts = defaultdict(list)
    for host in hosts:
        if host.device_id is not None:
            device_id_to_hosts[host.device_id].append(host)
    return dict(device_id_to_hosts)

"""
Database query helpers for network map generation.
"""
import logging
from collections import defaultdict
from ipaddress import ip_network
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, String, or_

from models import Host, Port, Connection, RouteHop, ARPEntry, VLANConfig, DeviceIdentity, AgentObservation, Agent

logger = logging.getLogger(__name__)


def _json_int_list_contains(column, value: int):
    serialized = column.cast(String)
    return or_(
        serialized.contains(f"[{value}]"),
        serialized.contains(f"[{value},"),
        serialized.contains(f", {value},"),
        serialized.contains(f",{value},"),
        serialized.contains(f", {value}]"),
        serialized.contains(f",{value}]"),
    )


async def fetch_hosts(
    db: AsyncSession,
    vlan_filter: Optional[int] = None,
    include_inactive: bool = False,
    source_origin: Optional[str] = None,
    observed_by_agent_id: Optional[int] = None,
) -> list:
    """Fetch hosts with optional filters."""
    query = select(Host)
    if not include_inactive:
        query = query.where(Host.is_active.is_(True))
    if vlan_filter is not None:
        query = query.where(Host.vlan_id == vlan_filter)
    if source_origin:
        query = query.where(Host.source_origins.cast(String).contains(f'"{source_origin}"'))
    if observed_by_agent_id is not None:
        query = query.where(_json_int_list_contains(Host.observed_by_agent_ids, observed_by_agent_id))
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


async def fetch_connections(
    db: AsyncSession,
    source_origin: Optional[str] = None,
    observed_by_agent_id: Optional[int] = None,
) -> list:
    """Fetch all connection records."""
    query = select(Connection)
    if source_origin:
        query = query.where(Connection.source_origin == source_origin)
    if observed_by_agent_id is not None:
        query = query.where(Connection.observer_agent_id == observed_by_agent_id)
    result = await db.execute(query)
    return result.scalars().all()


async def fetch_current_agent_observations(
    db: AsyncSession,
    observed_by_agent_id: Optional[int] = None,
    relationship_types: Optional[list[str]] = None,
    min_confidence: Optional[int] = None,
) -> list:
    """Fetch current agent observations used for topology relationship edges."""
    query = select(AgentObservation).where(
        AgentObservation.is_current.is_(True),
        AgentObservation.relationship_type.is_not(None),
    )
    if observed_by_agent_id is not None:
        query = query.where(AgentObservation.agent_id == observed_by_agent_id)
    if relationship_types:
        query = query.where(AgentObservation.relationship_type.in_(relationship_types))
    if min_confidence is not None:
        query = query.where(AgentObservation.confidence >= min_confidence)
    result = await db.execute(query)
    return result.scalars().all()


async def fetch_agents_by_ids(db: AsyncSession, agent_ids: list[int]) -> dict[int, Agent]:
    """Fetch agents keyed by ID for collector/vantage map nodes."""
    if not agent_ids:
        return {}
    result = await db.execute(select(Agent).where(Agent.id.in_(sorted(set(agent_ids)))))
    return {agent.id: agent for agent in result.scalars().all()}


def _is_groupable_network(network) -> bool:
    """Return true for networks useful as map grouping containers."""
    max_prefix = 30 if network.version == 4 else 126
    return (
        0 < network.prefixlen <= max_prefix
        and not network.is_loopback
        and not network.is_link_local
        and not network.is_multicast
        and not network.is_reserved
        and not network.is_unspecified
    )


async def fetch_observed_networks(
    db: AsyncSession,
    observed_by_agent_id: Optional[int] = None,
) -> list:
    """Fetch current agent-observed networks for map subnet grouping."""
    query = select(AgentObservation).where(
        AgentObservation.is_current.is_(True),
        AgentObservation.observation_type.in_(("address", "route")),
    )
    if observed_by_agent_id is not None:
        query = query.where(AgentObservation.agent_id == observed_by_agent_id)

    result = await db.execute(query)
    networks = set()
    for observation in result.scalars().all():
        payload = observation.payload or {}
        candidates = []
        if observation.observation_type == "address":
            ip_address = payload.get("ip_address")
            prefix_length = payload.get("prefix_length")
            if ip_address and prefix_length is not None:
                candidates.append(f"{ip_address}/{prefix_length}")
        elif observation.observation_type == "route":
            destination = payload.get("destination")
            if destination and destination != "default" and "/" in destination:
                candidates.append(destination)

        for candidate in candidates:
            try:
                network = ip_network(candidate, strict=False)
            except ValueError:
                continue
            if _is_groupable_network(network):
                networks.add(network)

    return sorted(networks, key=lambda network: (network.version, int(network.network_address), network.prefixlen))


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

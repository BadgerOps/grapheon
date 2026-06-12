"""
Database query helpers for network map generation.
"""
import logging
from collections import defaultdict
from ipaddress import ip_address, ip_network
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, String, or_

from models import Host, Port, Connection, RouteHop, ARPEntry, VLANConfig, DeviceIdentity, AgentObservation, Agent, NetworkGroup, EntityEvidence

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


async def fetch_network_groups(
    db: AsyncSession,
    include_hidden: bool = True,
    source: Optional[str] = None,
    q: Optional[str] = None,
) -> list[NetworkGroup]:
    """Fetch saved network grouping hints."""
    query = select(NetworkGroup).order_by(NetworkGroup.cidr)
    if not include_hidden:
        query = query.where(NetworkGroup.is_hidden.is_(False))
    if source:
        query = query.where(NetworkGroup.source == source)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(
                NetworkGroup.cidr.ilike(pattern),
                NetworkGroup.label.ilike(pattern),
                NetworkGroup.description.ilike(pattern),
            )
        )
    result = await db.execute(query)
    return result.scalars().all()


def parse_network_group_networks(network_groups: list[NetworkGroup]) -> tuple[list, dict[str, NetworkGroup]]:
    """Parse valid saved group CIDRs into networks and an exact-CIDR lookup."""
    networks = []
    group_by_cidr = {}
    for group in network_groups:
        try:
            network = ip_network(group.cidr, strict=False)
        except ValueError:
            logger.warning("Ignoring invalid saved network group CIDR: %s", group.cidr)
            continue
        canonical = str(network)
        networks.append(network)
        group_by_cidr[canonical] = group
    return networks, group_by_cidr


def filter_hosts_by_hidden_networks(hosts: list, hidden_networks: list) -> tuple[list, int]:
    """Remove hosts whose IP falls inside any hidden saved network group."""
    if not hidden_networks:
        return hosts, 0

    visible_hosts = []
    hidden_count = 0
    for host in hosts:
        try:
            addr = ip_address(host.ip_address)
        except ValueError:
            visible_hosts.append(host)
            continue
        if any(addr.version == network.version and addr in network for network in hidden_networks):
            hidden_count += 1
        else:
            visible_hosts.append(host)
    return visible_hosts, hidden_count


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
    include_historical: bool = False,
) -> list:
    """Fetch current agent observations used for topology relationship edges."""
    query = select(AgentObservation).where(AgentObservation.relationship_type.is_not(None))
    if not include_historical:
        query = query.where(AgentObservation.is_current.is_(True))
    if observed_by_agent_id is not None:
        query = query.where(AgentObservation.agent_id == observed_by_agent_id)
    if relationship_types:
        query = query.where(AgentObservation.relationship_type.in_(relationship_types))
    if min_confidence is not None:
        query = query.where(AgentObservation.confidence >= min_confidence)
    result = await db.execute(query)
    return result.scalars().all()


async def fetch_entity_evidence(
    db: AsyncSession,
    *,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    relationship_types: Optional[list[str]] = None,
    source_origin: Optional[str] = None,
    source_types: Optional[list[str]] = None,
    observer_agent_id: Optional[int] = None,
    min_confidence: Optional[int] = None,
    is_current: Optional[bool] = True,
    skip: int = 0,
    limit: int = 100,
) -> tuple[int, list[EntityEvidence]]:
    """Fetch entity evidence with map-oriented filters."""
    filters = []
    if entity_type:
        filters.append(EntityEvidence.entity_type == entity_type)
    if entity_id is not None:
        filters.append(EntityEvidence.entity_id == entity_id)
    if relationship_types:
        filters.append(EntityEvidence.relationship_type.in_(relationship_types))
    if source_origin:
        filters.append(EntityEvidence.source_origin == source_origin)
    if source_types:
        filters.append(EntityEvidence.source_type.in_(source_types))
    if observer_agent_id is not None:
        filters.append(EntityEvidence.observer_agent_id == observer_agent_id)
    if min_confidence is not None:
        filters.append(EntityEvidence.confidence >= min_confidence)
    if is_current is not None:
        filters.append(EntityEvidence.is_current.is_(is_current))

    count_query = select(func.count(EntityEvidence.id))
    query = select(EntityEvidence)
    if filters:
        count_query = count_query.where(*filters)
        query = query.where(*filters)

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(
        query.order_by(
            EntityEvidence.is_current.desc(),
            EntityEvidence.last_seen_at.desc(),
            EntityEvidence.confidence.desc(),
            EntityEvidence.id.desc(),
        )
        .offset(skip)
        .limit(limit)
    )
    return total, result.scalars().all()


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
        AgentObservation.observation_type.in_(("address", "route", "topology_evidence")),
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
        elif observation.observation_type == "topology_evidence":
            if payload.get("evidence_type") == "network_segment" and payload.get("network"):
                candidates.append(payload["network"])

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

"""
Network visualization API endpoints.

Thin orchestrator that delegates to the ``network`` package for
node/edge building, DB queries, styling, validation, and legacy format
conversion. Keeps the three endpoints (/map, /routes, /subnets) and
coordinates their data-fetching + assembly.
"""

import logging
import time
from typing import Optional, Dict, Any
from collections import defaultdict
from ipaddress import ip_network

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth.dependencies import require_any_authenticated
from models import NetworkGroup, User
from network.constants import COMPOUND_NODE_TYPES
from network.validators import get_observed_subnet
from network.queries import (
    fetch_hosts,
    fetch_vlan_configs,
    fetch_network_groups,
    filter_hosts_by_hidden_networks,
    parse_network_group_networks,
    fetch_arp_segments,
    fetch_connections,
    fetch_current_agent_observations,
    fetch_agents_by_ids,
    fetch_observed_networks,
    fetch_port_counts,
    fetch_device_identities,
    fetch_route_hops,
    fetch_entity_evidence,
    build_device_id_to_hosts,
)
from network.nodes import build_all_nodes
from network.edges import build_all_edges, add_agent_topology_edges
from network.legacy_format import build_legacy_response
from schemas import EntityEvidenceResponse

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/api/network", tags=["network"])

TOPOLOGY_EVIDENCE_RELATIONSHIPS = {
    "l2_neighbor",
    "switch_port_attachment",
    "mac_ip_binding",
    "dhcp_lease",
    "dns_name",
    "route",
    "flow_relationship",
    "network_segment",
}


class NetworkGroupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cidr: str = Field(..., min_length=1, max_length=64)
    label: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    is_expected: bool = True
    is_hidden: bool = False
    confidence: int = Field(100, ge=0, le=100)
    metadata: Optional[dict[str, Any]] = None


class NetworkGroupUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cidr: Optional[str] = Field(None, min_length=1, max_length=64)
    label: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    is_expected: Optional[bool] = None
    is_hidden: Optional[bool] = None
    confidence: Optional[int] = Field(None, ge=0, le=100)
    metadata: Optional[dict[str, Any]] = None


@router.get("/groups")
async def list_network_groups(
    include_hidden: bool = Query(True, description="Include hidden groups"),
    source: Optional[str] = Query(None, description="Filter by group source"),
    q: Optional[str] = Query(None, description="Search CIDR, label, or description"),
    user: User = Depends(require_any_authenticated),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """List saved network grouping definitions."""
    groups = await fetch_network_groups(
        db,
        include_hidden=include_hidden,
        source=source,
        q=q,
    )
    return {
        "items": [_network_group_response(group) for group in groups],
        "total": len(groups),
    }


@router.post("/groups", status_code=status.HTTP_201_CREATED)
async def create_network_group(
    payload: NetworkGroupCreate,
    user: User = Depends(require_any_authenticated),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Create a manual network grouping definition."""
    cidr = _normalize_network_group_cidr(payload.cidr)
    group = NetworkGroup(
        cidr=cidr,
        label=_clean_optional_text(payload.label),
        description=_clean_optional_text(payload.description),
        source="manual",
        confidence=payload.confidence,
        is_expected=payload.is_expected,
        is_hidden=payload.is_hidden,
        group_metadata=payload.metadata,
    )
    db.add(group)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Network group already exists for {cidr}",
        ) from exc
    await db.refresh(group)
    return _network_group_response(group)


@router.patch("/groups/{group_id}")
async def update_network_group(
    group_id: int,
    payload: NetworkGroupUpdate,
    user: User = Depends(require_any_authenticated),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Update a saved network grouping definition."""
    group = await db.get(NetworkGroup, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Network group not found")
    if group.source != "manual":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only manual network groups can be updated",
        )

    values = payload.model_dump(exclude_unset=True)
    if "cidr" in values:
        group.cidr = _normalize_network_group_cidr(values["cidr"])
    if "label" in values:
        group.label = _clean_optional_text(values["label"])
    if "description" in values:
        group.description = _clean_optional_text(values["description"])
    if "is_expected" in values:
        group.is_expected = values["is_expected"]
    if "is_hidden" in values:
        group.is_hidden = values["is_hidden"]
    if "confidence" in values:
        group.confidence = values["confidence"]
    if "metadata" in values:
        group.group_metadata = values["metadata"]

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Network group already exists for {group.cidr}",
        ) from exc
    await db.refresh(group)
    return _network_group_response(group)


@router.delete("/groups/{group_id}")
async def delete_network_group(
    group_id: int,
    user: User = Depends(require_any_authenticated),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Delete a manual network grouping definition."""
    group = await db.get(NetworkGroup, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Network group not found")
    if group.source != "manual":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only manual network groups can be deleted",
        )
    await db.delete(group)
    await db.commit()
    return {"status": "deleted", "id": group_id}


@router.get("/evidence")
async def list_network_evidence(
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    entity_id: Optional[int] = Query(None, description="Filter by entity ID"),
    relationship_types: Optional[list[str]] = Query(None, description="Filter by relationship/evidence types"),
    source_origin: Optional[str] = Query(None, description="Filter by source origin"),
    source_types: Optional[list[str]] = Query(None, description="Filter by evidence source type"),
    observer_agent_id: Optional[int] = Query(None, description="Filter by observing agent ID"),
    min_confidence: Optional[int] = Query(None, ge=0, le=100, description="Minimum confidence"),
    is_current: Optional[bool] = Query(True, description="Filter current/historical evidence"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    user: User = Depends(require_any_authenticated),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """List map-oriented field and relationship evidence."""
    total, items = await fetch_entity_evidence(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        relationship_types=relationship_types,
        source_origin=source_origin,
        source_types=source_types,
        observer_agent_id=observer_agent_id,
        min_confidence=min_confidence,
        is_current=is_current,
        skip=skip,
        limit=limit,
    )
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [
            EntityEvidenceResponse.model_validate(item).model_dump(mode="json")
            for item in items
        ],
    }


# ── Main map endpoint ────────────────────────────────────────────────

@router.get("/map")
async def get_network_map(
    subnet_filter: Optional[str] = Query(None, description="Filter by subnet CIDR"),
    segment_filter: Optional[str] = Query(None, description="Filter by segment/interface name"),
    vlan_filter: Optional[int] = Query(None, description="Filter by VLAN ID"),
    include_inactive: bool = Query(False, description="Include inactive hosts"),
    subnet_prefix: Optional[int] = Query(None, ge=8, le=32, description="Optional fallback subnet prefix for grouping when no observed/configured CIDR matches"),
    network_cidrs: Optional[list[str]] = Query(None, description="Operator-provided CIDR hints for map grouping"),
    group_by: str = Query("subnet", description="Grouping mode: 'subnet', 'segment', or 'vlan'"),
    layout_mode: str = Query("grouped", description="Layout hint: 'hierarchical', 'grouped', or 'force'"),
    format: str = Query("cytoscape", description="Response format: 'cytoscape' or 'legacy'"),
    show_internet: str = Query("cloud", description="Public IP handling: 'cloud', 'hide', or 'show'"),
    route_through_gateway: bool = Query(False, description="Route cross-subnet edges through gateway nodes"),
    source_origin: Optional[str] = Query(None, description="Filter map data by source origin"),
    observed_by_agent_id: Optional[int] = Query(None, description="Filter agent-observed data by collector agent ID"),
    relationship_types: Optional[list[str]] = Query(None, description="Agent relationship edge types to include"),
    evidence_sources: Optional[list[str]] = Query(None, description="Evidence source types to include"),
    min_confidence: Optional[int] = Query(None, ge=0, le=100, description="Minimum agent relationship confidence"),
    include_historical_evidence: bool = Query(False, description="Include stale/removed topology evidence observations"),
    include_collector_nodes: bool = Query(False, description="Include passive-agent collector/vantage nodes"),
    user: User = Depends(require_any_authenticated),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get network topology data for visualization.

    Returns Cytoscape.js elements with compound node hierarchy
    (VLAN → Subnet → Host). Supports legacy vis-network format via
    ``format=legacy``.
    """
    start_time = time.perf_counter()
    logger.debug("=" * 60)
    logger.debug("NETWORK MAP GENERATION STARTED")
    logger.debug(f"Parameters: group_by={group_by}, layout_mode={layout_mode}, format={format}")

    # ── Step 1: Fetch hosts ──────────────────────────────────────
    step_start = time.perf_counter()
    hosts = await fetch_hosts(
        db,
        vlan_filter,
        include_inactive,
        source_origin=source_origin,
        observed_by_agent_id=observed_by_agent_id,
    )
    logger.debug(f"[1/7] Fetched {len(hosts)} hosts in {_ms(step_start)}")

    # ── Step 2: Fetch VLAN configs + saved network groups ─────────
    step_start = time.perf_counter()
    vlan_configs = await fetch_vlan_configs(db)
    subnet_to_vlan = _build_subnet_to_vlan(vlan_configs)
    network_groups = await fetch_network_groups(db, include_hidden=True)
    hidden_networks, _ = parse_network_group_networks([
        group for group in network_groups if group.is_hidden
    ])
    visible_network_group_networks, network_group_by_cidr = parse_network_group_networks([
        group for group in network_groups if not group.is_hidden
    ])
    hosts, hidden_host_count = filter_hosts_by_hidden_networks(hosts, hidden_networks)
    logger.debug(
        f"[2/7] Loaded {len(vlan_configs)} VLAN configs, "
        f"{len(network_groups)} network groups, hid {hidden_host_count} hosts in {_ms(step_start)}"
    )

    # ── Step 3: Fetch ARP entries for segment info ───────────────
    step_start = time.perf_counter()
    ip_to_segment = await fetch_arp_segments(db) if group_by == "segment" else {}
    logger.debug(f"[3/7] ARP segment mapping: {len(ip_to_segment)} entries in {_ms(step_start)}")

    # ── Step 4: Fetch connections ────────────────────────────────
    step_start = time.perf_counter()
    connections = await fetch_connections(
        db,
        source_origin=source_origin,
        observed_by_agent_id=observed_by_agent_id,
    )
    logger.debug(f"[4/7] Fetched {len(connections)} connections in {_ms(step_start)}")

    # ── Step 5: Batch port counts (single GROUP BY query) ────────
    step_start = time.perf_counter()
    port_counts = await fetch_port_counts(db, [h.id for h in hosts])
    logger.debug(f"[5/7] Batch port counts for {len(hosts)} hosts in {_ms(step_start)}")

    # ── Step 5.5: Fetch DeviceIdentity data for gateway combining ─
    step_start = time.perf_counter()
    device_id_to_hosts = build_device_id_to_hosts(hosts)
    device_identities = (
        await fetch_device_identities(db) if device_id_to_hosts else {}
    )
    logger.debug(f"[5.5/7] Loaded {len(device_identities)} device identities in {_ms(step_start)}")

    # ── Step 5.75: Fetch agent-observed subnet boundaries ─────────
    step_start = time.perf_counter()
    agent_observed_networks = await fetch_observed_networks(
        db,
        observed_by_agent_id=observed_by_agent_id,
    )
    observed_networks = _merge_networks(
        _parse_network_cidrs(network_cidrs or [])
        + _parse_network_cidrs([subnet_filter] if subnet_filter else [])
        + visible_network_group_networks
        + list(subnet_to_vlan.keys())
        + agent_observed_networks
    )
    logger.debug(f"[5.75/7] Loaded {len(observed_networks)} observed networks in {_ms(step_start)}")

    # ── Step 6: Build Cytoscape nodes ────────────────────────────
    step_start = time.perf_counter()
    (
        nodes,
        seen_vlans,
        seen_subnets,
        ip_to_host_id,
        shared_gateway_nodes,
        shared_gateway_devices,
        public_ip_count,
        gateway_subnet_edges,
    ) = build_all_nodes(
        hosts=hosts,
        vlan_configs=vlan_configs,
        port_counts=port_counts,
        device_id_to_hosts=device_id_to_hosts,
        device_identities=device_identities,
        subnet_prefix=subnet_prefix,
        subnet_filter=subnet_filter,
        segment_filter=segment_filter,
        show_internet=show_internet,
        ip_to_segment=ip_to_segment,
        subnet_to_vlan=subnet_to_vlan,
        observed_networks=observed_networks,
        network_group_by_cidr=network_group_by_cidr,
    )

    # ── Step 7: Build edges from connections ──────────────────────
    edges, edge_stats = build_all_edges(
        connections=connections,
        hosts=hosts,
        nodes=nodes,
        ip_to_host_id=ip_to_host_id,
        show_internet=show_internet,
        route_through_gateway=route_through_gateway,
        subnet_prefix=subnet_prefix,
        shared_gateway_nodes=shared_gateway_nodes,
        shared_gateway_devices=shared_gateway_devices,
        observed_networks=observed_networks,
    )

    # Prepend gateway-to-subnet edges (created during node building)
    edges = gateway_subnet_edges + edges

    agent_edge_stats = {
        "collector_interface": 0,
        "arp_neighbor": 0,
        "connection_remote": 0,
        "route_gateway": 0,
    }
    should_build_agent_topology = (
        include_collector_nodes
        or bool(relationship_types)
        or bool(evidence_sources)
    )
    if should_build_agent_topology:
        active_relationship_types = set(relationship_types or [])
        if evidence_sources and not active_relationship_types:
            active_relationship_types.update(TOPOLOGY_EVIDENCE_RELATIONSHIPS)
        if active_relationship_types or include_collector_nodes:
            active_relationship_types.add("collector_interface")
        agent_observations = await fetch_current_agent_observations(
            db,
            observed_by_agent_id=observed_by_agent_id,
            relationship_types=sorted(active_relationship_types),
            min_confidence=min_confidence,
            include_historical=include_historical_evidence,
        )
        if evidence_sources:
            source_filter = {source.lower() for source in evidence_sources}
            agent_observations = [
                observation
                for observation in agent_observations
                if (observation.payload or {}).get("source", "agent").lower() in source_filter
                or observation.relationship_type not in TOPOLOGY_EVIDENCE_RELATIONSHIPS
            ]
        agents_by_id = await fetch_agents_by_ids(
            db,
            [observation.agent_id for observation in agent_observations],
        )
        agent_edge_stats = add_agent_topology_edges(
            nodes=nodes,
            edges=edges,
            observations=agent_observations,
            agents_by_id=agents_by_id,
            ip_to_host_id=ip_to_host_id,
            include_collector_nodes=include_collector_nodes,
        )

    logger.debug(
        f"[6-7/7] Built {len(nodes)} nodes, {len(edges)} edges "
        f"({edge_stats['internet_conn_count']} internet-routed) in {_ms(step_start)}"
    )

    # ── Build response ───────────────────────────────────────────
    total_duration = (time.perf_counter() - start_time) * 1000

    host_count = sum(
        1 for n in nodes
        if n["data"].get("type") not in COMPOUND_NODE_TYPES
        and not n["data"].get("is_shared_gateway")
    )
    stats = {
        "total_hosts": host_count,
        "total_edges": len(edges),
        "vlans": len(seen_vlans),
        "subnets": len(seen_subnets),
        "cross_vlan_edges": edge_stats["cross_vlan_count"],
        "cross_subnet_edges": edge_stats["cross_subnet_count"],
        "internet_connections": edge_stats["internet_conn_count"],
        "public_ip_hosts": public_ip_count,
        "shared_gateways": len(shared_gateway_nodes),
        "agent_topology_edges": sum(agent_edge_stats.values()),
        "agent_edge_counts": agent_edge_stats,
        "topology_evidence_edges": sum(
            count
            for relationship_type, count in agent_edge_stats.items()
            if relationship_type in TOPOLOGY_EVIDENCE_RELATIONSHIPS
        ),
        "observed_networks": [str(network) for network in observed_networks],
        "saved_network_groups": [
            _network_group_summary(group)
            for group in network_groups
        ],
        "hidden_network_groups": len(hidden_networks),
        "hidden_hosts": hidden_host_count,
        "unresolved_network_groups": sum(
            1
            for subnet_id in seen_subnets
            if subnet_id.startswith("subnet_unresolved-")
        ),
        "show_internet": show_internet,
        "group_mode": group_by,
        "layout_mode": layout_mode,
        "generation_time_ms": round(total_duration, 1),
    }

    logger.debug("=" * 60)
    logger.info(
        f"NETWORK MAP COMPLETE: {host_count} hosts, {len(seen_vlans)} VLANs, "
        f"{len(seen_subnets)} subnets, {len(edges)} edges, "
        f"{edge_stats['internet_conn_count']} internet-routed in {total_duration:.1f}ms"
    )
    logger.debug("=" * 60)

    if format == "legacy":
        return build_legacy_response(nodes, edges, seen_subnets, stats, subnet_prefix)

    return {
        "elements": {
            "nodes": nodes,
            "edges": edges,
        },
        "stats": stats,
    }


# ── Routes endpoint ──────────────────────────────────────────────────

@router.get("/routes")
async def get_network_routes(
    destination: Optional[str] = Query(None, description="Filter by destination IP"),
    user: User = Depends(require_any_authenticated),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get traceroute-derived topology data.

    Returns paths from source to destination hosts.
    """
    start_time = time.perf_counter()
    logger.info(f"ROUTE DATA GENERATION - destination={destination}")

    hops = await fetch_route_hops(db, destination)

    # Group hops by trace_id
    traces = defaultdict(list)
    for hop in hops:
        traces[hop.trace_id].append({
            "hop_number": hop.hop_number,
            "ip": hop.hop_ip,
            "hostname": hop.hostname,
            "rtt_ms": [hop.rtt_ms_1, hop.rtt_ms_2, hop.rtt_ms_3],
            "avg_rtt": sum(filter(None, [hop.rtt_ms_1, hop.rtt_ms_2, hop.rtt_ms_3])) / 3
            if any([hop.rtt_ms_1, hop.rtt_ms_2, hop.rtt_ms_3]) else None,
        })

    # Build path edges (Cytoscape format)
    path_edges = []
    for trace_id, trace_hops in traces.items():
        sorted_hops = sorted(trace_hops, key=lambda x: x["hop_number"])
        for i in range(len(sorted_hops) - 1):
            if sorted_hops[i]["ip"] and sorted_hops[i + 1]["ip"]:
                path_edges.append({
                    "data": {
                        "id": f"route_{trace_id}_{i}",
                        "source_ip": sorted_hops[i]["ip"],
                        "target_ip": sorted_hops[i + 1]["ip"],
                        "connection_type": "route",
                        "trace_id": trace_id,
                        "hop": i + 1,
                        "rtt_diff": (sorted_hops[i + 1].get("avg_rtt") or 0) - (sorted_hops[i].get("avg_rtt") or 0),
                        "tooltip": f"Hop {i+1}: {sorted_hops[i]['ip']} → {sorted_hops[i+1]['ip']}",
                    }
                })

    total_duration = (time.perf_counter() - start_time) * 1000
    logger.info(f"ROUTES COMPLETE: {len(traces)} traces, {len(path_edges)} path edges in {total_duration:.1f}ms")

    return {
        "traces": dict(traces),
        "path_edges": path_edges,
        "stats": {
            "total_traces": len(traces),
            "total_hops": len(hops),
            "total_path_edges": len(path_edges),
            "generation_time_ms": round(total_duration, 1),
        },
    }


# ── Subnets summary endpoint ────────────────────────────────────────

@router.get("/subnets")
async def get_subnets(
    prefix: Optional[int] = Query(None, ge=8, le=32, description="Optional fallback subnet prefix length"),
    network_cidrs: Optional[list[str]] = Query(None, description="Operator-provided CIDR hints for subnet grouping"),
    user: User = Depends(require_any_authenticated),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get a summary of detected subnets with VLAN association."""
    start_time = time.perf_counter()

    hosts = await fetch_hosts(db, include_inactive=False)
    vlan_configs = await fetch_vlan_configs(db)
    subnet_to_vlan = _build_subnet_to_vlan(vlan_configs)
    network_groups = await fetch_network_groups(db, include_hidden=True)
    hidden_networks, _ = parse_network_group_networks([
        group for group in network_groups if group.is_hidden
    ])
    visible_network_group_networks, network_group_by_cidr = parse_network_group_networks([
        group for group in network_groups if not group.is_hidden
    ])
    hosts, hidden_host_count = filter_hosts_by_hidden_networks(hosts, hidden_networks)
    agent_observed_networks = await fetch_observed_networks(db)
    observed_networks = _merge_networks(
        _parse_network_cidrs(network_cidrs or [])
        + visible_network_group_networks
        + list(subnet_to_vlan.keys())
        + agent_observed_networks
    )

    # Batch port counts (replaces N+1 per-host queries)
    port_counts = await fetch_port_counts(db, [h.id for h in hosts])

    subnets = defaultdict(lambda: {
        "hosts": [], "open_ports": 0, "device_types": defaultdict(int),
        "vlan_id": None, "vlan_name": None,
    })

    for host in hosts:
        subnet = get_observed_subnet(host.ip_address, prefix, observed_networks)
        subnets[subnet]["hosts"].append(host.ip_address)
        if host.device_type:
            subnets[subnet]["device_types"][host.device_type] += 1
        if host.vlan_id is not None and subnets[subnet]["vlan_id"] is None:
            subnets[subnet]["vlan_id"] = host.vlan_id
            subnets[subnet]["vlan_name"] = host.vlan_name
        subnets[subnet]["open_ports"] += port_counts.get(host.id, 0)

    subnet_list = []
    for subnet, data in subnets.items():
        network_group = network_group_by_cidr.get(subnet)
        subnet_list.append({
            "subnet": subnet,
            "label": network_group.label if network_group and network_group.label else subnet,
            "network_group_id": network_group.id if network_group else None,
            "network_group_source": network_group.source if network_group else None,
            "network_group_confidence": network_group.confidence if network_group else None,
            "network_group_expected": network_group.is_expected if network_group else None,
            "host_count": len(data["hosts"]),
            "hosts": data["hosts"],
            "open_ports": data["open_ports"],
            "device_types": dict(data["device_types"]),
            "vlan_id": data["vlan_id"],
            "vlan_name": data["vlan_name"],
        })

    subnet_list.sort(key=lambda x: x["host_count"], reverse=True)

    total_duration = (time.perf_counter() - start_time) * 1000
    return {
        "subnets": subnet_list,
        "total_subnets": len(subnet_list),
        "observed_networks": [str(network) for network in observed_networks],
        "saved_network_groups": [
            _network_group_summary(group)
            for group in network_groups
        ],
        "hidden_network_groups": len(hidden_networks),
        "hidden_hosts": hidden_host_count,
        "generation_time_ms": round(total_duration, 1),
    }


# ── Helpers ──────────────────────────────────────────────────────────

def _ms(step_start: float) -> str:
    """Format elapsed time since *step_start* as '12.3ms'."""
    return f"{(time.perf_counter() - step_start) * 1000:.1f}ms"


def _build_subnet_to_vlan(vlan_configs: dict) -> dict:
    """Build an ip_network → VLANConfig lookup from VLAN subnet_cidrs."""
    subnet_to_vlan = {}
    for vid, vconfig in vlan_configs.items():
        for cidr in (vconfig.subnet_cidrs or []):
            try:
                subnet_to_vlan[ip_network(cidr, strict=False)] = vconfig
            except ValueError:
                pass
    return subnet_to_vlan


def _normalize_network_group_cidr(cidr: str) -> str:
    try:
        return str(ip_network(str(cidr).strip(), strict=False))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid CIDR: {cidr}",
        ) from exc


def _clean_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _network_group_response(group: NetworkGroup) -> dict:
    return {
        "id": group.id,
        "cidr": group.cidr,
        "label": group.label,
        "description": group.description,
        "source": group.source,
        "confidence": group.confidence,
        "is_expected": group.is_expected,
        "is_hidden": group.is_hidden,
        "metadata": group.group_metadata,
        "created_at": group.created_at,
        "updated_at": group.updated_at,
    }


def _network_group_summary(group: NetworkGroup) -> dict:
    return {
        "id": group.id,
        "cidr": group.cidr,
        "label": group.label,
        "source": group.source,
        "confidence": group.confidence,
        "is_expected": group.is_expected,
        "is_hidden": group.is_hidden,
    }


def _parse_network_cidrs(network_cidrs: list[str]) -> list:
    """Parse operator-provided CIDR hints, ignoring invalid values."""
    networks = []
    for raw_value in network_cidrs:
        for candidate in str(raw_value).replace(",", " ").split():
            try:
                networks.append(ip_network(candidate, strict=False))
            except ValueError:
                logger.warning("Ignoring invalid network CIDR hint: %s", candidate)
    return networks


def _merge_networks(networks: list) -> list:
    """De-duplicate networks while keeping deterministic ordering."""
    unique = set(networks)
    return sorted(
        unique,
        key=lambda network: (network.version, int(network.network_address), network.prefixlen),
    )

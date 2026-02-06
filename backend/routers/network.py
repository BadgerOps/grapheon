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

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from network.constants import COMPOUND_NODE_TYPES
from network.validators import get_subnet
from network.queries import (
    fetch_hosts,
    fetch_vlan_configs,
    fetch_arp_segments,
    fetch_connections,
    fetch_port_counts,
    fetch_device_identities,
    fetch_route_hops,
    build_device_id_to_hosts,
)
from network.nodes import build_all_nodes
from network.edges import build_all_edges
from network.legacy_format import build_legacy_response

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/api/network", tags=["network"])


# ── Main map endpoint ────────────────────────────────────────────────

@router.get("/map")
async def get_network_map(
    subnet_filter: Optional[str] = Query(None, description="Filter by subnet CIDR"),
    segment_filter: Optional[str] = Query(None, description="Filter by segment/interface name"),
    vlan_filter: Optional[int] = Query(None, description="Filter by VLAN ID"),
    include_inactive: bool = Query(False, description="Include inactive hosts"),
    subnet_prefix: int = Query(24, ge=8, le=32, description="Subnet prefix for grouping"),
    group_by: str = Query("subnet", description="Grouping mode: 'subnet', 'segment', or 'vlan'"),
    layout_mode: str = Query("grouped", description="Layout hint: 'hierarchical', 'grouped', or 'force'"),
    format: str = Query("cytoscape", description="Response format: 'cytoscape' or 'legacy'"),
    show_internet: str = Query("cloud", description="Public IP handling: 'cloud', 'hide', or 'show'"),
    route_through_gateway: bool = Query(False, description="Route cross-subnet edges through gateway nodes"),
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
    hosts = await fetch_hosts(db, vlan_filter, include_inactive)
    logger.debug(f"[1/7] Fetched {len(hosts)} hosts in {_ms(step_start)}")

    # ── Step 2: Fetch VLAN configs + subnet→VLAN lookup ──────────
    step_start = time.perf_counter()
    vlan_configs = await fetch_vlan_configs(db)
    subnet_to_vlan = _build_subnet_to_vlan(vlan_configs)
    logger.debug(f"[2/7] Loaded {len(vlan_configs)} VLAN configs in {_ms(step_start)}")

    # ── Step 3: Fetch ARP entries for segment info ───────────────
    step_start = time.perf_counter()
    ip_to_segment = await fetch_arp_segments(db) if group_by == "segment" else {}
    logger.debug(f"[3/7] ARP segment mapping: {len(ip_to_segment)} entries in {_ms(step_start)}")

    # ── Step 4: Fetch connections ────────────────────────────────
    step_start = time.perf_counter()
    connections = await fetch_connections(db)
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
    )

    # Prepend gateway-to-subnet edges (created during node building)
    edges = gateway_subnet_edges + edges

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
    prefix: int = Query(24, ge=8, le=32, description="Subnet prefix length"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get a summary of detected subnets with VLAN association."""
    start_time = time.perf_counter()

    hosts = await fetch_hosts(db, include_inactive=False)

    # Batch port counts (replaces N+1 per-host queries)
    port_counts = await fetch_port_counts(db, [h.id for h in hosts])

    subnets = defaultdict(lambda: {
        "hosts": [], "open_ports": 0, "device_types": defaultdict(int),
        "vlan_id": None, "vlan_name": None,
    })

    for host in hosts:
        subnet = get_subnet(host.ip_address, prefix)
        subnets[subnet]["hosts"].append(host.ip_address)
        if host.device_type:
            subnets[subnet]["device_types"][host.device_type] += 1
        if host.vlan_id is not None and subnets[subnet]["vlan_id"] is None:
            subnets[subnet]["vlan_id"] = host.vlan_id
            subnets[subnet]["vlan_name"] = host.vlan_name
        subnets[subnet]["open_ports"] += port_counts.get(host.id, 0)

    subnet_list = []
    for subnet, data in subnets.items():
        subnet_list.append({
            "subnet": subnet,
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

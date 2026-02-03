"""
Network visualization API endpoints.

Provides data for network topology visualization including:
- Host nodes with metadata
- Connection edges between hosts
- Traceroute paths
- Subnet grouping
"""

import logging
import time
from typing import Optional, Dict, Any
from collections import defaultdict
from ipaddress import ip_address, ip_network
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from database import get_db
from models import Host, Port, Connection, RouteHop

# Set up verbose logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

router = APIRouter(prefix="/api/network", tags=["network"])


def get_subnet(ip: str, prefix: int = 24) -> str:
    """Extract subnet from IP address."""
    try:
        addr = ip_address(ip)
        if addr.version == 4:
            network = ip_network(f"{ip}/{prefix}", strict=False)
            return str(network.network_address)
        return "ipv6"
    except Exception:
        return "unknown"


def get_node_color(host: Host) -> str:
    """Determine node color based on device type and OS."""
    if host.device_type:
        type_colors = {
            "router": "#f97316",      # Orange
            "switch": "#8b5cf6",      # Purple
            "firewall": "#ef4444",    # Red
            "server": "#3b82f6",      # Blue
            "workstation": "#22c55e", # Green
            "printer": "#ec4899",     # Pink
            "iot": "#06b6d4",         # Cyan
        }
        return type_colors.get(host.device_type.lower(), "#6b7280")

    if host.os_family:
        os_colors = {
            "linux": "#f97316",
            "windows": "#3b82f6",
            "macos": "#6b7280",
            "network": "#8b5cf6",
        }
        return os_colors.get(host.os_family.lower(), "#6b7280")

    return "#6b7280"  # Gray default


def get_node_shape(host: Host) -> str:
    """Determine node shape based on device type."""
    if host.device_type:
        type_shapes = {
            "router": "diamond",
            "switch": "triangle",
            "firewall": "star",
            "server": "box",
            "workstation": "dot",
            "printer": "square",
            "iot": "hexagon",
        }
        return type_shapes.get(host.device_type.lower(), "dot")
    return "dot"


@router.get("/map")
async def get_network_map(
    subnet_filter: Optional[str] = Query(None, description="Filter by subnet (e.g., 192.168.1.0)"),
    include_inactive: bool = Query(False, description="Include inactive hosts"),
    group_by_subnet: bool = Query(True, description="Group nodes by subnet"),
    subnet_prefix: int = Query(24, ge=8, le=32, description="Subnet prefix for grouping"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get network topology data for visualization.

    Returns nodes (hosts) and edges (connections) formatted for vis-network.
    """
    start_time = time.perf_counter()
    logger.info("=" * 60)
    logger.info("NETWORK MAP GENERATION STARTED")
    logger.info(f"Parameters: subnet_filter={subnet_filter}, include_inactive={include_inactive}, group_by_subnet={group_by_subnet}")

    # Step 1: Fetch hosts
    step_start = time.perf_counter()
    logger.info("[1/5] Fetching hosts from database...")

    query = select(Host)
    if not include_inactive:
        query = query.where(Host.is_active.is_(True))

    result = await db.execute(query)
    hosts = result.scalars().all()

    logger.info(f"[1/5] Fetched {len(hosts)} hosts in {(time.perf_counter() - step_start)*1000:.1f}ms")

    # Step 2: Fetch connections
    step_start = time.perf_counter()
    logger.info("[2/5] Fetching connections from database...")

    conn_result = await db.execute(select(Connection))
    connections = conn_result.scalars().all()

    logger.info(f"[2/5] Fetched {len(connections)} connections in {(time.perf_counter() - step_start)*1000:.1f}ms")

    # Step 3: Fetch ports for open port count
    step_start = time.perf_counter()
    logger.info("[3/5] Counting open ports per host...")

    port_counts = {}
    for host in hosts:
        port_result = await db.execute(
            select(func.count(Port.id)).where(
                and_(Port.host_id == host.id, Port.state == "open")
            )
        )
        port_counts[host.id] = port_result.scalar() or 0

    logger.info(f"[3/5] Counted ports for {len(hosts)} hosts in {(time.perf_counter() - step_start)*1000:.1f}ms")

    # Step 4: Build nodes
    step_start = time.perf_counter()
    logger.info("[4/5] Building node data structures...")

    nodes = []
    subnets = defaultdict(list)
    ip_to_host_id = {}

    for host in hosts:
        subnet = get_subnet(host.ip_address, subnet_prefix)

        # Filter by subnet if specified
        if subnet_filter and subnet != subnet_filter:
            continue

        ip_to_host_id[host.ip_address] = host.id

        # Build node label
        label_parts = [host.ip_address]
        if host.hostname:
            label_parts.insert(0, host.hostname)

        node = {
            "id": host.id,
            "label": "\n".join(label_parts),
            "title": _build_node_tooltip(host, port_counts.get(host.id, 0)),
            "color": get_node_color(host),
            "shape": get_node_shape(host),
            "size": 15 + min(port_counts.get(host.id, 0), 20),  # Size based on open ports
            "group": subnet if group_by_subnet else "default",
            # Additional metadata
            "ip": host.ip_address,
            "hostname": host.hostname,
            "os": host.os_name,
            "device_type": host.device_type,
            "open_ports": port_counts.get(host.id, 0),
            "subnet": subnet,
        }
        nodes.append(node)
        subnets[subnet].append(host.id)

    logger.info(f"[4/5] Built {len(nodes)} nodes across {len(subnets)} subnets in {(time.perf_counter() - step_start)*1000:.1f}ms")

    # Step 5: Build edges from connections
    step_start = time.perf_counter()
    logger.info("[5/5] Building edge data from connections...")

    edges = []
    edge_set = set()  # Avoid duplicate edges

    for conn in connections:
        # Get host IDs for local and remote IPs
        from_id = ip_to_host_id.get(conn.local_ip)
        to_id = ip_to_host_id.get(conn.remote_ip)

        if from_id and to_id and from_id != to_id:
            # Create a canonical edge key to avoid duplicates
            edge_key = tuple(sorted([from_id, to_id]))
            if edge_key not in edge_set:
                edge_set.add(edge_key)
                edges.append({
                    "id": f"{from_id}-{to_id}",
                    "from": from_id,
                    "to": to_id,
                    "title": f"{conn.local_ip}:{conn.local_port} → {conn.remote_ip}:{conn.remote_port}",
                    "color": {"color": "#64748b", "opacity": 0.6},
                    "width": 1,
                })

    logger.info(f"[5/5] Built {len(edges)} unique edges in {(time.perf_counter() - step_start)*1000:.1f}ms")

    # Build subnet groups for clustering
    groups = {}
    for subnet, host_ids in subnets.items():
        groups[subnet] = {
            "id": subnet,
            "label": f"{subnet}/{subnet_prefix}",
            "host_count": len(host_ids),
            "color": _get_subnet_color(subnet),
        }

    total_duration = (time.perf_counter() - start_time) * 1000
    logger.info("=" * 60)
    logger.info("NETWORK MAP GENERATION COMPLETE")
    logger.info(f"Total time: {total_duration:.1f}ms | Nodes: {len(nodes)} | Edges: {len(edges)} | Subnets: {len(subnets)}")
    logger.info("=" * 60)

    return {
        "nodes": nodes,
        "edges": edges,
        "groups": groups,
        "stats": {
            "total_hosts": len(nodes),
            "total_connections": len(edges),
            "subnets": len(subnets),
            "generation_time_ms": round(total_duration, 1),
        },
    }


def _build_node_tooltip(host: Host, open_ports: int) -> str:
    """Build HTML tooltip for a node."""
    lines = [f"<b>{host.ip_address}</b>"]

    if host.hostname:
        lines.append(f"Hostname: {host.hostname}")
    if host.mac_address:
        lines.append(f"MAC: {host.mac_address}")
    if host.vendor:
        lines.append(f"Vendor: {host.vendor}")
    if host.os_name:
        os_str = host.os_name
        if host.os_version:
            os_str += f" {host.os_version}"
        lines.append(f"OS: {os_str}")
    if host.device_type:
        lines.append(f"Type: {host.device_type}")

    lines.append(f"Open Ports: {open_ports}")
    lines.append(f"Last Seen: {host.last_seen.strftime('%Y-%m-%d %H:%M')}")

    return "<br>".join(lines)


def _get_subnet_color(subnet: str) -> str:
    """Generate a consistent color for a subnet."""
    # Simple hash-based color
    colors = [
        "#3b82f6", "#22c55e", "#f97316", "#8b5cf6",
        "#ec4899", "#06b6d4", "#eab308", "#ef4444",
    ]
    hash_val = sum(ord(c) for c in subnet)
    return colors[hash_val % len(colors)]


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
    logger.info("=" * 60)
    logger.info("ROUTE DATA GENERATION STARTED")
    logger.info(f"Parameters: destination={destination}")

    # Fetch route hops
    query = select(RouteHop)
    if destination:
        query = query.where(RouteHop.dest_ip == destination)

    result = await db.execute(query.order_by(RouteHop.trace_id, RouteHop.hop_number))
    hops = result.scalars().all()

    logger.info(f"Fetched {len(hops)} route hops")

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

    # Build path edges
    path_edges = []
    for trace_id, trace_hops in traces.items():
        sorted_hops = sorted(trace_hops, key=lambda x: x["hop_number"])
        for i in range(len(sorted_hops) - 1):
            if sorted_hops[i]["ip"] and sorted_hops[i + 1]["ip"]:
                path_edges.append({
                    "from_ip": sorted_hops[i]["ip"],
                    "to_ip": sorted_hops[i + 1]["ip"],
                    "trace_id": trace_id,
                    "hop": i + 1,
                    "rtt_diff": (sorted_hops[i + 1].get("avg_rtt") or 0) - (sorted_hops[i].get("avg_rtt") or 0),
                })

    total_duration = (time.perf_counter() - start_time) * 1000
    logger.info(f"ROUTE DATA GENERATION COMPLETE - {len(traces)} traces, {len(path_edges)} path edges in {total_duration:.1f}ms")
    logger.info("=" * 60)

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


@router.get("/subnets")
async def get_subnets(
    prefix: int = Query(24, ge=8, le=32, description="Subnet prefix length"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get a summary of detected subnets.
    """
    start_time = time.perf_counter()
    logger.info(f"Generating subnet summary with prefix /{prefix}")

    result = await db.execute(select(Host).where(Host.is_active.is_(True)))
    hosts = result.scalars().all()

    subnets = defaultdict(lambda: {"hosts": [], "open_ports": 0, "device_types": defaultdict(int)})

    for host in hosts:
        subnet = get_subnet(host.ip_address, prefix)
        subnets[subnet]["hosts"].append(host.ip_address)
        if host.device_type:
            subnets[subnet]["device_types"][host.device_type] += 1

        # Count open ports
        port_result = await db.execute(
            select(func.count(Port.id)).where(
                and_(Port.host_id == host.id, Port.state == "open")
            )
        )
        subnets[subnet]["open_ports"] += port_result.scalar() or 0

    # Convert to list format
    subnet_list = []
    for subnet, data in subnets.items():
        subnet_list.append({
            "subnet": f"{subnet}/{prefix}",
            "host_count": len(data["hosts"]),
            "hosts": data["hosts"],
            "open_ports": data["open_ports"],
            "device_types": dict(data["device_types"]),
        })

    # Sort by host count descending
    subnet_list.sort(key=lambda x: x["host_count"], reverse=True)

    total_duration = (time.perf_counter() - start_time) * 1000
    logger.info(f"Subnet summary complete: {len(subnet_list)} subnets in {total_duration:.1f}ms")

    return {
        "subnets": subnet_list,
        "total_subnets": len(subnet_list),
        "generation_time_ms": round(total_duration, 1),
    }

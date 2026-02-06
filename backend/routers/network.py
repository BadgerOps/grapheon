"""
Network visualization API endpoints.

Provides data for network topology visualization including:
- Host nodes with metadata (Cytoscape.js elements format)
- Compound node hierarchy: VLAN → Subnet → Host
- Connection edges between hosts
- Traceroute paths
- Multiple layout mode support
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
from models import Host, Port, Connection, RouteHop, ARPEntry, VLANConfig, DeviceIdentity

# Set up verbose logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

router = APIRouter(prefix="/api/network", tags=["network"])


# ── Device type styling ──────────────────────────────────────────────

DEVICE_STYLES = {
    "router":      {"color": "#f97316", "shape": "diamond",   "size": 50},
    "switch":      {"color": "#8b5cf6", "shape": "triangle",  "size": 45},
    "firewall":    {"color": "#ef4444", "shape": "star",      "size": 45},
    "server":      {"color": "#3b82f6", "shape": "rectangle", "size": 40},
    "workstation": {"color": "#22c55e", "shape": "ellipse",   "size": 35},
    "printer":     {"color": "#ec4899", "shape": "rectangle", "size": 35},
    "iot":         {"color": "#06b6d4", "shape": "hexagon",   "size": 35},
}

DEFAULT_STYLE = {"color": "#6b7280", "shape": "ellipse", "size": 30}

# RFC1918 and other non-routable private ranges
PRIVATE_NETWORKS = [
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("127.0.0.0/8"),       # Loopback
    ip_network("169.254.0.0/16"),     # Link-local
    ip_network("100.64.0.0/10"),      # CGNAT / Shared address space
    ip_network("fc00::/7"),           # IPv6 ULA
    ip_network("fe80::/10"),          # IPv6 link-local
    ip_network("::1/128"),            # IPv6 loopback
]


def is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private/non-routable (RFC1918, loopback, link-local, CGNAT)."""
    try:
        addr = ip_address(ip_str)
        # Python's is_private covers most cases but we also want CGNAT (100.64/10)
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            return True
        for net in PRIVATE_NETWORKS:
            if addr in net:
                return True
        return False
    except (ValueError, TypeError):
        return True  # Treat unparseable IPs as private (don't route to Internet)


def get_subnet(ip: str, prefix: int = 24) -> str:
    """Extract subnet CIDR from IP address."""
    try:
        addr = ip_address(ip)
        if addr.version == 4:
            network = ip_network(f"{ip}/{prefix}", strict=False)
            return str(network)
        return "ipv6::/128"
    except Exception:
        return "unknown/0"


def _get_device_style(host: Host) -> dict:
    """Get Cytoscape node styling for a device type."""
    if host.device_type:
        return DEVICE_STYLES.get(host.device_type.lower(), DEFAULT_STYLE)
    return DEFAULT_STYLE


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
    if host.vlan_id is not None:
        vlan_str = f"VLAN {host.vlan_id}"
        if host.vlan_name:
            vlan_str += f" ({host.vlan_name})"
        lines.append(vlan_str)
    lines.append(f"Open Ports: {open_ports}")
    lines.append(f"Last Seen: {host.last_seen.strftime('%Y-%m-%d %H:%M')}")
    return "<br>".join(lines)


# ── Color palettes ───────────────────────────────────────────────────

VLAN_COLORS = [
    "#3b82f6", "#22c55e", "#f97316", "#8b5cf6",
    "#ec4899", "#06b6d4", "#eab308", "#ef4444",
    "#14b8a6", "#f43f5e",
]

SUBNET_COLORS = [
    "#60a5fa", "#4ade80", "#fb923c", "#a78bfa",
    "#f472b6", "#22d3ee", "#facc15", "#f87171",
]


def _get_vlan_color(vlan_id: int, config_color: str = None) -> str:
    """Get color for a VLAN — use configured color or auto-assign."""
    if config_color:
        return config_color
    return VLAN_COLORS[vlan_id % len(VLAN_COLORS)]


def _get_subnet_color(subnet: str) -> str:
    """Generate a consistent color for a subnet."""
    hash_val = sum(ord(c) for c in subnet)
    return SUBNET_COLORS[hash_val % len(SUBNET_COLORS)]


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
    show_internet: str = Query("cloud", description="Public IP handling: 'cloud' (route through gateway to Internet node), 'hide' (exclude public IPs entirely), 'show' (show public IPs as regular hosts)"),
    route_through_gateway: bool = Query(False, description="Route cross-subnet edges through gateway nodes instead of direct connections"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get network topology data for visualization.

    Returns elements formatted for Cytoscape.js with compound node hierarchy:
    VLAN (parent) → Subnet (child parent) → Host (leaf node).

    Supports legacy vis-network format via format=legacy parameter.
    """
    start_time = time.perf_counter()
    logger.info("=" * 60)
    logger.info("NETWORK MAP GENERATION STARTED")
    logger.info(f"Parameters: group_by={group_by}, layout_mode={layout_mode}, format={format}")

    # ── Step 1: Fetch hosts ──────────────────────────────────────
    step_start = time.perf_counter()
    query = select(Host)
    if not include_inactive:
        query = query.where(Host.is_active.is_(True))
    if vlan_filter is not None:
        query = query.where(Host.vlan_id == vlan_filter)

    result = await db.execute(query)
    hosts = result.scalars().all()
    logger.info(f"[1/6] Fetched {len(hosts)} hosts in {(time.perf_counter() - step_start)*1000:.1f}ms")

    # ── Step 2: Fetch VLAN configs ───────────────────────────────
    step_start = time.perf_counter()
    vlan_result = await db.execute(select(VLANConfig).order_by(VLANConfig.vlan_id))
    vlan_configs = {v.vlan_id: v for v in vlan_result.scalars().all()}

    # Build subnet → VLAN lookup from configs
    subnet_to_vlan = {}
    for vid, vconfig in vlan_configs.items():
        for cidr in (vconfig.subnet_cidrs or []):
            try:
                subnet_to_vlan[ip_network(cidr, strict=False)] = vconfig
            except ValueError:
                pass
    logger.info(f"[2/6] Loaded {len(vlan_configs)} VLAN configs in {(time.perf_counter() - step_start)*1000:.1f}ms")

    # ── Step 3: Fetch ARP entries for segment info ───────────────
    step_start = time.perf_counter()
    ip_to_segment = {}
    if group_by == "segment":
        arp_result = await db.execute(select(ARPEntry))
        for arp_entry in arp_result.scalars().all():
            if arp_entry.interface:
                ip_to_segment[arp_entry.ip_address] = arp_entry.interface
    logger.info(f"[3/6] ARP segment mapping: {len(ip_to_segment)} entries in {(time.perf_counter() - step_start)*1000:.1f}ms")

    # ── Step 4: Fetch connections ────────────────────────────────
    step_start = time.perf_counter()
    conn_result = await db.execute(select(Connection))
    connections = conn_result.scalars().all()
    logger.info(f"[4/6] Fetched {len(connections)} connections in {(time.perf_counter() - step_start)*1000:.1f}ms")

    # ── Step 5: Fetch port counts ────────────────────────────────
    step_start = time.perf_counter()
    port_counts = {}
    for host in hosts:
        port_result = await db.execute(
            select(func.count(Port.id)).where(
                and_(Port.host_id == host.id, Port.state == "open")
            )
        )
        port_counts[host.id] = port_result.scalar() or 0
    logger.info(f"[5/7] Counted ports for {len(hosts)} hosts in {(time.perf_counter() - step_start)*1000:.1f}ms")

    # ── Step 5.5: Fetch DeviceIdentity data for gateway combining ─
    step_start = time.perf_counter()
    device_id_to_hosts = defaultdict(list)  # device_id → [host, ...]
    for host in hosts:
        if host.device_id is not None:
            device_id_to_hosts[host.device_id].append(host)

    # Fetch DeviceIdentity records for shared gateways
    device_identities = {}
    if device_id_to_hosts:
        di_result = await db.execute(
            select(DeviceIdentity).where(DeviceIdentity.is_active.is_(True))
        )
        for di in di_result.scalars().all():
            device_identities[di.id] = di
    logger.info(f"[5.5/7] Loaded {len(device_identities)} device identities in {(time.perf_counter() - step_start)*1000:.1f}ms")

    # ── Step 6: Build Cytoscape elements ─────────────────────────
    step_start = time.perf_counter()

    nodes = []          # All Cytoscape node elements
    edges = []          # All Cytoscape edge elements
    ip_to_host_id = {}  # For edge building
    seen_vlans = {}     # vlan_id → compound node data
    seen_subnets = {}   # subnet_cidr → compound node data

    # Public IP grouping: track which hosts are public
    public_ips_node_id = "public_ips"
    public_ip_node_added = False
    public_ip_count = 0

    # Track hosts that belong to a shared gateway (device_id based)
    # These will be replaced by a single shared gateway node later
    shared_gw_host_ids = set()  # host IDs that are part of a shared gateway

    # Pre-compute: which device_ids have multi-subnet gateways?
    shared_gateway_devices = {}  # device_id → list of gateway hosts
    for device_id, di_hosts in device_id_to_hosts.items():
        gateway_hosts = [
            h for h in di_hosts
            if h.device_type and h.device_type.lower() == "router"
        ]
        if len(gateway_hosts) > 1:
            # Multiple router-type hosts share a device_id → shared gateway
            shared_gateway_devices[device_id] = gateway_hosts
            for h in gateway_hosts:
                shared_gw_host_ids.add(h.id)

    for host in hosts:
        subnet_cidr = get_subnet(host.ip_address, subnet_prefix)
        segment = ip_to_segment.get(host.ip_address, None)

        # Apply filters
        if subnet_filter and not subnet_cidr.startswith(subnet_filter):
            continue
        if segment_filter and segment != segment_filter:
            continue

        # ── Handle public IP hosts ────────────────────────────
        host_is_public = not is_private_ip(host.ip_address)

        if host_is_public and show_internet == "cloud":
            # In cloud mode, public IP hosts are folded into the Internet node.
            # Don't create individual nodes — they'll be represented by the
            # Internet cloud + gateway routing from connections.
            # NOTE: do NOT add to ip_to_host_id — Case 2 in edge building
            # handles public IPs by routing through gateway → Internet.
            continue

        if host_is_public and show_internet == "hide":
            # Don't add to ip_to_host_id so no edges reference this host.
            continue

        if host_is_public and show_internet == "show":
            # Group all public IPs into a "Public IPs" compound node
            public_ip_count += 1
            ip_to_host_id[host.ip_address] = host.id
            if not public_ip_node_added:
                nodes.append({
                    "data": {
                        "id": public_ips_node_id,
                        "label": "Internet / Public IPs",
                        "type": "public_ips",
                        "color": "#0ea5e9",
                    }
                })
                public_ip_node_added = True

            # Create node parented to the public IPs compound
            style = _get_device_style(host)
            label_parts = []
            if host.hostname:
                label_parts.append(host.hostname)
            label_parts.append(host.ip_address)

            nodes.append({
                "data": {
                    "id": str(host.id),
                    "parent": public_ips_node_id,
                    "label": "\n".join(label_parts),
                    "tooltip": _build_node_tooltip(host, port_counts.get(host.id, 0)),
                    "ip": host.ip_address,
                    "hostname": host.hostname,
                    "mac": host.mac_address,
                    "os": host.os_name,
                    "os_family": host.os_family,
                    "device_type": host.device_type or "unknown",
                    "vendor": host.vendor,
                    "open_ports": port_counts.get(host.id, 0),
                    "subnet": "public",
                    "segment": None,
                    "vlan_id": None,
                    "vlan_name": None,
                    "is_gateway": False,
                    "is_public": True,
                    "color": style["color"],
                    "node_shape": style["shape"],
                    "node_size": style["size"] + min(port_counts.get(host.id, 0), 15),
                }
            })
            continue

        # ── Skip hosts that will be represented by a shared gateway node ─
        if host.id in shared_gw_host_ids:
            # Don't create an individual node — a shared gateway node
            # will be created after the loop for this device.
            # ip_to_host_id will be set to the shared_gw_node_id later.
            continue

        # Map this host's IP → node ID (only for hosts that have nodes created)
        ip_to_host_id[host.ip_address] = host.id

        # ── Resolve VLAN for this host ───────────────────────
        host_vlan_id = host.vlan_id
        host_vlan_name = host.vlan_name
        host_vlan_color = None

        # If host doesn't have VLAN assigned, try to infer from subnet → VLAN mapping
        if host_vlan_id is None and host.ip_address:
            try:
                addr = ip_address(host.ip_address)
                for net, vconfig in subnet_to_vlan.items():
                    if addr in net:
                        host_vlan_id = vconfig.vlan_id
                        host_vlan_name = vconfig.vlan_name
                        host_vlan_color = vconfig.color
                        break
            except ValueError:
                pass

        # Use configured VLAN color
        if host_vlan_id is not None and host_vlan_id in vlan_configs:
            host_vlan_color = vlan_configs[host_vlan_id].color

        # ── Create VLAN compound node (if not yet created) ───
        vlan_node_id = None
        if host_vlan_id is not None:
            vlan_node_id = f"vlan_{host_vlan_id}"
            if vlan_node_id not in seen_vlans:
                label = host_vlan_name or f"VLAN {host_vlan_id}"
                seen_vlans[vlan_node_id] = True
                nodes.append({
                    "data": {
                        "id": vlan_node_id,
                        "label": f"{label} (VLAN {host_vlan_id})",
                        "type": "vlan",
                        "vlan_id": host_vlan_id,
                        "color": _get_vlan_color(host_vlan_id, host_vlan_color),
                    }
                })

        # ── Create Subnet compound node (if not yet created) ─
        subnet_node_id = f"subnet_{subnet_cidr}"
        if subnet_node_id not in seen_subnets:
            seen_subnets[subnet_node_id] = {
                "host_count": 0,
                "vlan_node_id": vlan_node_id,
            }
            subnet_data = {
                "id": subnet_node_id,
                "label": subnet_cidr,
                "type": "subnet",
                "subnet_cidr": subnet_cidr,
                "color": _get_subnet_color(subnet_cidr),
            }
            # Nest subnet inside VLAN compound
            if vlan_node_id:
                subnet_data["parent"] = vlan_node_id
            nodes.append({"data": subnet_data})

        seen_subnets[subnet_node_id]["host_count"] += 1

        # ── Create host leaf node ────────────────────────────
        style = _get_device_style(host)
        label_parts = []
        if host.hostname:
            label_parts.append(host.hostname)
        label_parts.append(host.ip_address)

        host_node = {
            "data": {
                "id": str(host.id),
                "parent": subnet_node_id,
                "label": "\n".join(label_parts),
                "tooltip": _build_node_tooltip(host, port_counts.get(host.id, 0)),
                # Device metadata
                "ip": host.ip_address,
                "hostname": host.hostname,
                "mac": host.mac_address,
                "os": host.os_name,
                "os_family": host.os_family,
                "device_type": host.device_type or "unknown",
                "vendor": host.vendor,
                "open_ports": port_counts.get(host.id, 0),
                # Network context
                "subnet": subnet_cidr,
                "segment": segment,
                "vlan_id": host_vlan_id,
                "vlan_name": host_vlan_name,
                "is_gateway": bool(host.device_type and host.device_type.lower() == "router"),
                "device_id": host.device_id,
                # Styling hints
                "color": style["color"],
                "node_shape": style["shape"],
                "node_size": style["size"] + min(port_counts.get(host.id, 0), 15),
            }
        }
        nodes.append(host_node)

    # ── Create shared gateway nodes (multi-homed routers) ───────
    # For each device_id with multiple gateway hosts, create ONE shared
    # gateway node that sits outside the subnet compounds, replacing the
    # individual gateway host nodes that were skipped above.
    shared_gateway_nodes = {}  # device_id → shared_gw_node_id

    for device_id, gateway_hosts in shared_gateway_devices.items():
        di = device_identities.get(device_id)
        gw_ips = sorted(h.ip_address for h in gateway_hosts)
        gw_subnets = sorted(set(
            get_subnet(h.ip_address, subnet_prefix) for h in gateway_hosts
        ))

        # Build label
        gw_name = di.name if di else gateway_hosts[0].hostname or "Shared Gateway"
        gw_label = f"{gw_name}\n" + " / ".join(gw_ips)

        # Build tooltip
        tooltip_lines = [f"<b>{gw_name}</b>", f"Type: Shared Gateway (Device ID: {device_id})"]
        tooltip_lines.append(f"IPs: {', '.join(gw_ips)}")
        tooltip_lines.append(f"Subnets: {', '.join(gw_subnets)}")
        if gateway_hosts[0].mac_address:
            tooltip_lines.append(f"MAC: {gateway_hosts[0].mac_address}")
        if gateway_hosts[0].vendor:
            tooltip_lines.append(f"Vendor: {gateway_hosts[0].vendor}")

        shared_gw_node_id = f"shared_gw_{device_id}"

        # Determine parent: if all gateways share a VLAN, nest under that VLAN
        # Otherwise, leave at top level (no parent)
        gw_vlan_ids = set()
        for h in gateway_hosts:
            if h.vlan_id is not None:
                gw_vlan_ids.add(h.vlan_id)
        parent = None
        # Don't nest in a single VLAN — shared gateways span VLANs by definition

        shared_gw_data = {
            "id": shared_gw_node_id,
            "label": gw_label,
            "tooltip": "<br>".join(tooltip_lines),
            "ip": " / ".join(gw_ips),
            "hostname": gw_name,
            "mac": gateway_hosts[0].mac_address,
            "os": gateway_hosts[0].os_name,
            "os_family": gateway_hosts[0].os_family,
            "device_type": "router",
            "vendor": gateway_hosts[0].vendor,
            "open_ports": sum(port_counts.get(h.id, 0) for h in gateway_hosts),
            "subnet": ", ".join(gw_subnets),
            "segment": None,
            "vlan_id": None,
            "vlan_name": None,
            "is_gateway": True,
            "is_shared_gateway": True,
            "device_id": device_id,
            "serves_subnets": gw_subnets,
            "color": "#f97316",
            "node_shape": "diamond",
            "node_size": 55,
        }
        if parent:
            shared_gw_data["parent"] = parent
        nodes.append({"data": shared_gw_data})
        shared_gateway_nodes[device_id] = shared_gw_node_id

        # Map each gateway host's IP to this shared node for edge building
        for h in gateway_hosts:
            ip_to_host_id[h.ip_address] = shared_gw_node_id

        # Create edges from shared gateway to each subnet it connects
        for subnet_cidr in gw_subnets:
            subnet_node_id = f"subnet_{subnet_cidr}"
            if subnet_node_id in seen_subnets:
                edges.append({
                    "data": {
                        "id": f"{shared_gw_node_id}-{subnet_node_id}",
                        "source": shared_gw_node_id,
                        "target": subnet_node_id,
                        "connection_type": "to_gateway",
                        "tooltip": f"{gw_name} → {subnet_cidr}",
                    }
                })

        logger.info(
            f"Created shared gateway node '{gw_name}' for device {device_id}: "
            f"{', '.join(gw_ips)} serving {', '.join(gw_subnets)}"
        )

    # ── Build edges from connections ──────────────────────────
    edge_set = set()
    cross_vlan_count = 0
    cross_subnet_count = 0
    internet_conn_count = 0

    # Build IP → (vlan, subnet) lookup for edge classification
    ip_context = {}
    for host in hosts:
        subnet_cidr_ctx = get_subnet(host.ip_address, subnet_prefix)
        ip_context[host.ip_address] = {
            "vlan_id": host.vlan_id,
            "subnet": subnet_cidr_ctx,
        }

    # ── Internet cloud + gateway routing ──────────────────────
    # When show_internet="cloud", public IPs are collapsed into a single
    # "Internet" node. Connections route: local_host → subnet gateway → Internet.
    #
    # Gateway detection per subnet:
    #   1) A host with device_type="router" in the same subnet
    #   2) Fall back to the .1 address if a host exists there
    #   3) Otherwise create a synthetic gateway node

    internet_node_id = "internet_cloud"
    internet_node_added = False
    # subnet_node_id → gateway_node_id
    subnet_gateways = {}
    # gateway_node_id → set of public IPs routed through it
    gateway_public_ips = defaultdict(set)
    # Edges from gateway → Internet (deduplicated)
    gateway_internet_edges = set()

    def _find_or_create_gateway(source_subnet_id: str, source_subnet_cidr: str):
        """Find the gateway for a subnet, or create a synthetic one."""
        nonlocal internet_node_added

        if source_subnet_id in subnet_gateways:
            return subnet_gateways[source_subnet_id]

        # Strategy 0: check if this subnet is served by a shared gateway
        for device_id, shared_gw_id in shared_gateway_nodes.items():
            gw_hosts = shared_gateway_devices.get(device_id, [])
            gw_subnets = [get_subnet(h.ip_address, subnet_prefix) for h in gw_hosts]
            if source_subnet_cidr in gw_subnets:
                subnet_gateways[source_subnet_id] = shared_gw_id
                return shared_gw_id

        # Strategy 1: look for a router node already in this subnet
        for n in nodes:
            d = n["data"]
            if d.get("parent") == source_subnet_id and d.get("is_gateway"):
                subnet_gateways[source_subnet_id] = d["id"]
                return d["id"]

        # Strategy 2: look for a host at .1 address in this subnet
        try:
            net = ip_network(source_subnet_cidr, strict=False)
            gw_ip = str(net.network_address + 1)  # e.g. 10.180.0.1
            if gw_ip in ip_to_host_id:
                gw_id = str(ip_to_host_id[gw_ip])
                subnet_gateways[source_subnet_id] = gw_id
                return gw_id
        except (ValueError, TypeError):
            pass

        # Strategy 3: create a synthetic gateway node
        try:
            net = ip_network(source_subnet_cidr, strict=False)
            gw_ip = str(net.network_address + 1)
        except (ValueError, TypeError):
            gw_ip = "?.?.?.1"

        gw_node_id = f"gw_{source_subnet_id}"
        nodes.append({
            "data": {
                "id": gw_node_id,
                "parent": source_subnet_id,
                "label": f"Gateway\n{gw_ip}",
                "tooltip": f"<b>Default Gateway</b><br>{gw_ip}<br>Inferred for {source_subnet_cidr}",
                "ip": gw_ip,
                "hostname": None,
                "mac": None,
                "os": None,
                "os_family": None,
                "device_type": "router",
                "vendor": None,
                "open_ports": 0,
                "subnet": source_subnet_cidr,
                "segment": None,
                "vlan_id": None,
                "vlan_name": None,
                "is_gateway": True,
                "is_synthetic": True,
                "color": "#f97316",
                "node_shape": "diamond",
                "node_size": 45,
            }
        })
        subnet_gateways[source_subnet_id] = gw_node_id
        return gw_node_id

    def _ensure_internet_node():
        """Add the Internet cloud node if not yet added."""
        nonlocal internet_node_added
        if not internet_node_added:
            nodes.append({
                "data": {
                    "id": internet_node_id,
                    "label": "Internet",
                    "type": "internet",
                    "device_type": "internet",
                    "color": "#0ea5e9",
                    "node_shape": "ellipse",
                    "node_size": 70,
                }
            })
            internet_node_added = True

    for conn in connections:
        from_id = ip_to_host_id.get(conn.local_ip)
        to_id = ip_to_host_id.get(conn.remote_ip)

        # ── Case 1: Both IPs are known internal hosts ─────────
        if from_id and to_id and from_id != to_id:
            edge_key = tuple(sorted([from_id, to_id]))
            if edge_key not in edge_set:
                edge_set.add(edge_key)

                from_ctx = ip_context.get(conn.local_ip, {})
                to_ctx = ip_context.get(conn.remote_ip, {})

                from_vlan = from_ctx.get("vlan_id")
                to_vlan = to_ctx.get("vlan_id")
                from_subnet = from_ctx.get("subnet")
                to_subnet = to_ctx.get("subnet")

                if from_vlan is not None and to_vlan is not None and from_vlan != to_vlan:
                    conn_type = "cross_vlan"
                    cross_vlan_count += 1
                elif from_subnet and to_subnet and from_subnet != to_subnet:
                    conn_type = "cross_subnet"
                    cross_subnet_count += 1
                else:
                    conn_type = "same_subnet"

                # Route cross-subnet/cross-VLAN through gateways when enabled
                if route_through_gateway and conn_type in ("cross_subnet", "cross_vlan"):
                    from_subnet_id = f"subnet_{from_subnet}"
                    to_subnet_id = f"subnet_{to_subnet}"

                    gw_from = _find_or_create_gateway(from_subnet_id, from_subnet)
                    gw_to = _find_or_create_gateway(to_subnet_id, to_subnet)

                    # Edge: source host → source gateway
                    hgw_key_from = tuple(sorted([str(from_id), str(gw_from)]))
                    if hgw_key_from not in edge_set:
                        edge_set.add(hgw_key_from)
                        edges.append({
                            "data": {
                                "id": f"{from_id}-{gw_from}",
                                "source": str(from_id),
                                "target": str(gw_from),
                                "connection_type": "to_gateway",
                                "protocol": conn.protocol or "tcp",
                                "tooltip": f"{conn.local_ip} → gateway ({from_subnet})",
                            }
                        })

                    # Edge: source gateway → target gateway
                    gw_gw_key = tuple(sorted([str(gw_from), str(gw_to)]))
                    if gw_gw_key not in edge_set:
                        edge_set.add(gw_gw_key)
                        edges.append({
                            "data": {
                                "id": f"{gw_from}-{gw_to}",
                                "source": str(gw_from),
                                "target": str(gw_to),
                                "connection_type": conn_type,
                                "protocol": conn.protocol or "tcp",
                                "tooltip": f"Gateway {from_subnet} → Gateway {to_subnet}",
                            }
                        })

                    # Edge: target gateway → target host
                    hgw_key_to = tuple(sorted([str(to_id), str(gw_to)]))
                    if hgw_key_to not in edge_set:
                        edge_set.add(hgw_key_to)
                        edges.append({
                            "data": {
                                "id": f"{gw_to}-{to_id}",
                                "source": str(gw_to),
                                "target": str(to_id),
                                "connection_type": "to_gateway",
                                "protocol": conn.protocol or "tcp",
                                "tooltip": f"gateway ({to_subnet}) → {conn.remote_ip}",
                            }
                        })
                else:
                    # Direct edge (same subnet or route_through_gateway disabled)
                    edge = {
                        "data": {
                            "id": f"{from_id}-{to_id}",
                            "source": str(from_id),
                            "target": str(to_id),
                            "connection_type": conn_type,
                            "protocol": conn.protocol or "tcp",
                            "port_info": f"{conn.local_port} → {conn.remote_port}" if conn.remote_port else str(conn.local_port),
                            "state": conn.state,
                            "tooltip": f"{conn.local_ip}:{conn.local_port} → {conn.remote_ip}:{conn.remote_port or '?'} ({conn.protocol or 'tcp'})",
                        }
                    }
                    edges.append(edge)
            continue

        # ── Case 2: Connection involves a public/external IP ──
        # Determine which side is local and which is external
        local_ip = None
        remote_ip = None
        if from_id and not to_id:
            local_ip = conn.local_ip
            remote_ip = conn.remote_ip
        elif to_id and not from_id:
            local_ip = conn.remote_ip
            remote_ip = conn.local_ip
        else:
            continue  # Neither side is a known host, skip

        # Check if remote is actually a public IP
        if is_private_ip(remote_ip):
            continue  # Private IP we just don't have in our hosts — skip

        # ── show_internet="hide" → drop all public connections
        if show_internet == "hide":
            continue

        # ── show_internet="cloud" → route through gateway to Internet node
        if show_internet == "cloud":
            internet_conn_count += 1

            # Find the source host's subnet compound node
            source_host_id = ip_to_host_id[local_ip]
            source_ctx = ip_context.get(local_ip, {})
            source_subnet_cidr = source_ctx.get("subnet", "unknown/0")
            source_subnet_id = f"subnet_{source_subnet_cidr}"

            # Find or create gateway for this subnet
            gw_id = _find_or_create_gateway(source_subnet_id, source_subnet_cidr)

            # Edge: local host → gateway (if not already connected)
            host_gw_key = tuple(sorted([str(source_host_id), str(gw_id)]))
            if host_gw_key not in edge_set:
                edge_set.add(host_gw_key)
                edges.append({
                    "data": {
                        "id": f"{source_host_id}-{gw_id}",
                        "source": str(source_host_id),
                        "target": str(gw_id),
                        "connection_type": "to_gateway",
                        "protocol": conn.protocol or "tcp",
                        "tooltip": f"{local_ip} → gateway (→ {remote_ip}:{conn.remote_port or '?'})",
                    }
                })

            # Track which public IPs go through this gateway
            gateway_public_ips[gw_id].add(remote_ip)

            # Ensure Internet node exists + create gateway→Internet edge (once per gateway)
            _ensure_internet_node()
            if gw_id not in gateway_internet_edges:
                gateway_internet_edges.add(gw_id)
                edges.append({
                    "data": {
                        "id": f"{gw_id}-{internet_node_id}",
                        "source": str(gw_id),
                        "target": internet_node_id,
                        "connection_type": "internet",
                        "tooltip": "Gateway → Internet",
                    }
                })

    # Update gateway→Internet edge tooltips with public IP counts
    for edge in edges:
        d = edge["data"]
        if d.get("connection_type") == "internet":
            gw = d["source"]
            pub_ips = gateway_public_ips.get(gw, set())
            count = len(pub_ips)
            sample = sorted(pub_ips)[:5]
            sample_str = ", ".join(sample)
            if count > 5:
                sample_str += f" (+{count - 5} more)"
            d["tooltip"] = f"Gateway → Internet ({count} ext. IPs)\n{sample_str}"
            d["public_ip_count"] = count

    logger.info(f"[6/7] Built {len(nodes)} elements, {len(edges)} edges ({internet_conn_count} internet-routed) in {(time.perf_counter() - step_start)*1000:.1f}ms")

    # ── Build response ───────────────────────────────────────────
    total_duration = (time.perf_counter() - start_time) * 1000

    compound_types = ("vlan", "subnet", "internet", "public_ips")
    host_count = sum(1 for n in nodes if n["data"].get("type") not in compound_types and not n["data"].get("is_shared_gateway"))
    stats = {
        "total_hosts": host_count,
        "total_edges": len(edges),
        "vlans": len(seen_vlans),
        "subnets": len(seen_subnets),
        "cross_vlan_edges": cross_vlan_count,
        "cross_subnet_edges": cross_subnet_count,
        "internet_connections": internet_conn_count,
        "public_ip_hosts": public_ip_count,
        "shared_gateways": len(shared_gateway_nodes),
        "show_internet": show_internet,
        "group_mode": group_by,
        "layout_mode": layout_mode,
        "generation_time_ms": round(total_duration, 1),
    }

    logger.info("=" * 60)
    logger.info(f"NETWORK MAP COMPLETE: {host_count} hosts, {len(seen_vlans)} VLANs, {len(seen_subnets)} subnets, {len(edges)} edges, {internet_conn_count} internet-routed in {total_duration:.1f}ms")
    logger.info("=" * 60)

    # ── Legacy format for backward compatibility ─────────────
    if format == "legacy":
        return _build_legacy_response(nodes, edges, seen_subnets, stats, subnet_prefix)

    return {
        "elements": {
            "nodes": nodes,
            "edges": edges,
        },
        "stats": stats,
    }


def _build_legacy_response(nodes, edges, seen_subnets, stats, subnet_prefix):
    """Build vis-network compatible response for backward compatibility."""
    legacy_nodes = []
    legacy_edges = []
    groups = {}

    for node in nodes:
        d = node["data"]
        if d.get("type") in ("vlan", "subnet"):
            # Compound nodes become groups
            groups[d["id"]] = {
                "id": d["id"],
                "label": d["label"],
                "host_count": seen_subnets.get(d["id"], {}).get("host_count", 0),
                "color": d.get("color", "#6b7280"),
            }
        else:
            legacy_nodes.append({
                "id": int(d["id"]),
                "label": d["label"],
                "title": d.get("tooltip", ""),
                "color": d.get("color", "#6b7280"),
                "shape": {"diamond": "diamond", "triangle": "triangle", "star": "star",
                          "rectangle": "box", "hexagon": "hexagon", "ellipse": "dot"
                          }.get(d.get("node_shape", "ellipse"), "dot"),
                "size": d.get("node_size", 15),
                "group": d.get("subnet", "unknown"),
                "ip": d.get("ip"),
                "hostname": d.get("hostname"),
                "os": d.get("os"),
                "device_type": d.get("device_type"),
                "open_ports": d.get("open_ports", 0),
                "subnet": d.get("subnet"),
                "segment": d.get("segment"),
                "is_gateway": d.get("is_gateway", False),
            })

    for edge in edges:
        d = edge["data"]
        is_cross = d.get("connection_type") in ("cross_vlan", "cross_subnet")
        legacy_edges.append({
            "id": d["id"],
            "from": int(d["source"]),
            "to": int(d["target"]),
            "title": d.get("tooltip", ""),
            "color": {"color": "#f59e0b" if is_cross else "#64748b", "opacity": 0.8 if is_cross else 0.6},
            "width": 2 if is_cross else 1,
            "dashes": [8, 4] if is_cross else False,
            "cross_segment": is_cross,
        })

    return {
        "nodes": legacy_nodes,
        "edges": legacy_edges,
        "groups": groups,
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

    query = select(RouteHop)
    if destination:
        query = query.where(RouteHop.dest_ip == destination)

    result = await db.execute(query.order_by(RouteHop.trace_id, RouteHop.hop_number))
    hops = result.scalars().all()

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

    result = await db.execute(select(Host).where(Host.is_active.is_(True)))
    hosts = result.scalars().all()

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

        port_result = await db.execute(
            select(func.count(Port.id)).where(
                and_(Port.host_id == host.id, Port.state == "open")
            )
        )
        subnets[subnet]["open_ports"] += port_result.scalar() or 0

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

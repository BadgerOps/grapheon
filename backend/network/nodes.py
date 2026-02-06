"""
Node-building logic for network visualization.

Extracts Cytoscape node element creation from the network router.
Builds compound and leaf nodes for hosts, VLANs, subnets, public IPs,
and shared gateways.
"""

from ipaddress import ip_address

from network.constants import (
    PUBLIC_IPS_NODE_ID,
    INTERNET_NODE_COLOR,
    MAX_NODE_SIZE_INCREMENT,
    ROUTER_COLOR,
)
from network.styles import (
    get_device_style,
    build_node_tooltip,
    get_vlan_color,
    get_subnet_color,
)
from network.validators import is_private_ip, get_subnet


def build_all_nodes(
    hosts,
    vlan_configs: dict,
    port_counts: dict,
    device_id_to_hosts: dict,
    device_identities: dict,
    subnet_prefix: int = 24,
    subnet_filter: str = None,
    segment_filter: str = None,
    show_internet: str = "cloud",
    ip_to_segment: dict = None,
    subnet_to_vlan: dict = None,
) -> tuple:
    """
    Build all Cytoscape node elements for the network map.

    Handles compound nodes (VLAN, Subnet, Public IPs) and leaf nodes (hosts).
    Combines multi-homed routers into shared gateway nodes.

    Args:
        hosts: List of Host objects from database
        vlan_configs: Dict mapping vlan_id → VLANConfig
        port_counts: Dict mapping host.id → open port count
        device_id_to_hosts: Dict mapping device_id → [hosts...]
        device_identities: Dict mapping device_id → DeviceIdentity
        subnet_prefix: Prefix for subnet CIDR calculation (default 24)
        subnet_filter: Optional filter for subnet CIDR
        segment_filter: Optional filter for segment/interface name
        show_internet: How to handle public IPs ("cloud", "hide", "show")
        ip_to_segment: Dict mapping IP address → segment/interface name
        subnet_to_vlan: Dict mapping ip_network → VLANConfig for subnet inference

    Returns:
        Tuple of (nodes, seen_vlans, seen_subnets, ip_to_host_id,
                  shared_gateway_nodes, shared_gateway_devices, public_ip_count)
        where:
            - nodes: List of Cytoscape node element dicts
            - seen_vlans: Dict tracking vlan_id → compound node data
            - seen_subnets: Dict tracking subnet_cidr → {host_count, vlan_node_id}
            - ip_to_host_id: Mapping of IP address → node ID for edge building
            - shared_gateway_nodes: Dict mapping device_id → shared_gw_node_id
            - shared_gateway_devices: Dict mapping device_id → [gateway hosts]
            - public_ip_count: Count of public IP hosts added to nodes
    """
    if ip_to_segment is None:
        ip_to_segment = {}
    if subnet_to_vlan is None:
        subnet_to_vlan = {}

    nodes = []
    ip_to_host_id = {}
    seen_vlans = {}
    seen_subnets = {}

    public_ip_node_added = False
    public_ip_count = 0

    # Pre-compute shared gateway devices (device_ids with multiple router hosts)
    shared_gw_host_ids = set()
    shared_gateway_devices = {}

    for device_id, di_hosts in device_id_to_hosts.items():
        gateway_hosts = [
            h for h in di_hosts
            if h.device_type and h.device_type.lower() == "router"
        ]
        if len(gateway_hosts) > 1:
            shared_gateway_devices[device_id] = gateway_hosts
            for h in gateway_hosts:
                shared_gw_host_ids.add(h.id)

    # Process each host
    for host in hosts:
        subnet_cidr = get_subnet(host.ip_address, subnet_prefix)
        segment = ip_to_segment.get(host.ip_address, None)

        # Apply filters
        if subnet_filter and not subnet_cidr.startswith(subnet_filter):
            continue
        if segment_filter and segment != segment_filter:
            continue

        # ── Handle public IP hosts ────────────────────────────────────
        host_is_public = not is_private_ip(host.ip_address)

        if host_is_public and show_internet == "cloud":
            # Cloud mode: public IPs are folded into Internet node
            # Don't create individual nodes — handled via gateway routing
            continue

        if host_is_public and show_internet == "hide":
            # Hide public IPs entirely
            continue

        if host_is_public and show_internet == "show":
            # Show as nodes under Public IPs compound
            _add_public_ip_node(
                nodes,
                host,
                port_counts,
                public_ip_count,
                public_ip_node_added,
            )
            public_ip_count += 1
            ip_to_host_id[host.ip_address] = host.id
            if not public_ip_node_added:
                public_ip_node_added = True
            continue

        # ── Skip hosts that will be replaced by shared gateway nodes ──
        if host.id in shared_gw_host_ids:
            continue

        # Map host IP to node ID for edge building
        ip_to_host_id[host.ip_address] = host.id

        # ── Resolve VLAN for this host ──────────────────────────────
        host_vlan_id = host.vlan_id
        host_vlan_name = host.vlan_name
        host_vlan_color = None

        # Infer VLAN from subnet if not explicitly set
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

        # ── Create VLAN compound node if needed ─────────────────────
        vlan_node_id = _build_vlan_compound(
            nodes,
            seen_vlans,
            host_vlan_id,
            host_vlan_name,
            host_vlan_color,
        )

        # ── Create Subnet compound node if needed ────────────────────
        subnet_node_id = _build_subnet_compound(
            nodes,
            seen_subnets,
            subnet_cidr,
            vlan_node_id,
        )

        seen_subnets[subnet_node_id]["host_count"] += 1

        # ── Create host leaf node ───────────────────────────────────
        _add_host_node(
            nodes,
            host,
            subnet_node_id,
            subnet_cidr,
            segment,
            host_vlan_id,
            host_vlan_name,
            port_counts,
        )

    # ── Create shared gateway nodes ─────────────────────────────────
    shared_gateway_nodes = {}
    gateway_subnet_edges = []

    for device_id, gateway_hosts in shared_gateway_devices.items():
        _add_shared_gateway_node(
            nodes,
            gateway_subnet_edges,
            shared_gateway_nodes,
            ip_to_host_id,
            seen_subnets,
            device_id,
            gateway_hosts,
            device_identities,
            port_counts,
            subnet_prefix,
        )

    return (
        nodes,
        seen_vlans,
        seen_subnets,
        ip_to_host_id,
        shared_gateway_nodes,
        shared_gateway_devices,
        public_ip_count,
        gateway_subnet_edges,
    )


def _add_public_ip_node(
    nodes: list,
    host,
    port_counts: dict,
    public_ip_count: int,
    public_ip_node_added: bool,
) -> None:
    """
    Add a public IP host node under the Public IPs compound node.

    Args:
        nodes: List to append node to
        host: Host object
        port_counts: Dict mapping host.id → open port count
        public_ip_count: Current count of public IPs (for reference)
        public_ip_node_added: Whether Public IPs compound was already created
    """
    # Create Public IPs compound if not already done
    if not public_ip_node_added:
        nodes.append({
            "data": {
                "id": PUBLIC_IPS_NODE_ID,
                "label": "Internet / Public IPs",
                "type": "public_ips",
                "color": INTERNET_NODE_COLOR,
            }
        })

    # Create host node under Public IPs compound
    style = get_device_style(host.device_type)
    label_parts = []
    if host.hostname:
        label_parts.append(host.hostname)
    label_parts.append(host.ip_address)

    nodes.append({
        "data": {
            "id": str(host.id),
            "parent": PUBLIC_IPS_NODE_ID,
            "label": "\n".join(label_parts),
            "tooltip": build_node_tooltip(host, port_counts.get(host.id, 0)),
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
            "node_size": style["size"] + min(port_counts.get(host.id, 0), MAX_NODE_SIZE_INCREMENT),
        }
    })


def _add_host_node(
    nodes: list,
    host,
    subnet_node_id: str,
    subnet_cidr: str,
    segment: str,
    host_vlan_id: int,
    host_vlan_name: str,
    port_counts: dict,
) -> None:
    """
    Add a regular host leaf node.

    Args:
        nodes: List to append node to
        host: Host object
        subnet_node_id: ID of parent subnet compound node
        subnet_cidr: Subnet CIDR string
        segment: Segment/interface name or None
        host_vlan_id: VLAN ID or None
        host_vlan_name: VLAN name or None
        port_counts: Dict mapping host.id → open port count
    """
    style = get_device_style(host.device_type)
    label_parts = []
    if host.hostname:
        label_parts.append(host.hostname)
    label_parts.append(host.ip_address)

    is_gateway = bool(host.device_type and host.device_type.lower() == "router")

    host_node = {
        "data": {
            "id": str(host.id),
            "parent": subnet_node_id,
            "label": "\n".join(label_parts),
            "tooltip": build_node_tooltip(host, port_counts.get(host.id, 0)),
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
            "is_gateway": is_gateway,
            "device_id": host.device_id,
            # Styling
            "color": style["color"],
            "node_shape": style["shape"],
            "node_size": style["size"] + min(port_counts.get(host.id, 0), MAX_NODE_SIZE_INCREMENT),
        }
    }
    nodes.append(host_node)


def _add_shared_gateway_node(
    nodes: list,
    edges: list,
    shared_gateway_nodes: dict,
    ip_to_host_id: dict,
    seen_subnets: dict,
    device_id: str,
    gateway_hosts: list,
    device_identities: dict,
    port_counts: dict,
    subnet_prefix: int,
) -> None:
    """
    Add a shared gateway node for a device with multiple router hosts.

    Creates a single node representing all gateway instances and maps
    their IPs to that shared node. Also creates edges from the shared
    gateway to each served subnet.

    Args:
        nodes: List to append gateway node to
        edges: List to append gateway-to-subnet edges to
        shared_gateway_nodes: Dict to store device_id → shared_gw_node_id mapping
        ip_to_host_id: Dict to update with gateway IP → node_id mappings
        seen_subnets: Dict of created subnets for edge creation
        device_id: Device ID of the shared gateway
        gateway_hosts: List of Host objects that are routers for this device
        device_identities: Dict mapping device_id → DeviceIdentity
        port_counts: Dict mapping host.id → open port count
        subnet_prefix: Prefix for subnet CIDR calculation
    """
    di = device_identities.get(device_id)
    gw_ips = sorted(h.ip_address for h in gateway_hosts)
    gw_subnets = sorted(set(
        get_subnet(h.ip_address, subnet_prefix) for h in gateway_hosts
    ))

    # Build display label
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

    # Shared gateways sit at top level (span multiple VLANs/subnets)
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
        "color": ROUTER_COLOR,
        "node_shape": "diamond",
        "node_size": 55,
    }

    nodes.append({"data": shared_gw_data})
    shared_gateway_nodes[device_id] = shared_gw_node_id

    # Map each gateway host IP to the shared node for edge building
    for h in gateway_hosts:
        ip_to_host_id[h.ip_address] = shared_gw_node_id

    # Create edges from shared gateway to each served subnet
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


def _build_vlan_compound(
    nodes: list,
    seen_vlans: dict,
    vlan_id: int,
    vlan_name: str,
    vlan_color: str,
) -> str:
    """
    Create a VLAN compound node if it doesn't exist.

    Args:
        nodes: List to append node to
        seen_vlans: Dict tracking created VLANs (modified in place)
        vlan_id: VLAN ID (can be None)
        vlan_name: VLAN name or None
        vlan_color: VLAN color or None

    Returns:
        VLAN node ID if created, or None if no VLAN
    """
    if vlan_id is None:
        return None

    vlan_node_id = f"vlan_{vlan_id}"
    if vlan_node_id not in seen_vlans:
        label = vlan_name or f"VLAN {vlan_id}"
        seen_vlans[vlan_node_id] = True
        nodes.append({
            "data": {
                "id": vlan_node_id,
                "label": f"{label} (VLAN {vlan_id})",
                "type": "vlan",
                "vlan_id": vlan_id,
                "color": get_vlan_color(vlan_id, vlan_color),
            }
        })

    return vlan_node_id


def _build_subnet_compound(
    nodes: list,
    seen_subnets: dict,
    subnet_cidr: str,
    vlan_node_id: str,
) -> str:
    """
    Create a Subnet compound node if it doesn't exist.

    Args:
        nodes: List to append node to
        seen_subnets: Dict tracking created subnets (modified in place)
        subnet_cidr: Subnet CIDR string (e.g., "192.168.1.0/24")
        vlan_node_id: Parent VLAN node ID or None

    Returns:
        Subnet node ID (always created or retrieved)
    """
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
            "color": get_subnet_color(subnet_cidr),
        }
        # Nest subnet inside VLAN if it has one
        if vlan_node_id:
            subnet_data["parent"] = vlan_node_id
        nodes.append({"data": subnet_data})

    return subnet_node_id

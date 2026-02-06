"""
Edge building and gateway resolution logic for network visualization.

Extracts edge-building and gateway resolution from the network router,
providing a reusable GatewayResolver class and build_all_edges function.
"""

from collections import defaultdict
from ipaddress import ip_network
from typing import Dict, List, Set, Tuple, Any

from network.constants import (
    INTERNET_NODE_ID,
    INTERNET_NODE_COLOR,
    MAX_PUBLIC_IP_SAMPLES,
    DEFAULT_GATEWAY_IP_OFFSET,
)
from network.validators import is_private_ip, get_subnet


class GatewayResolver:
    """
    Manages gateway discovery and creation for subnets.

    Implements 4-strategy gateway resolution:
    1. Check if subnet is served by a shared gateway device
    2. Look for an existing router node in the subnet
    3. Look for a host at the .1 address
    4. Create a synthetic gateway node

    Tracks state: subnet_gateways mapping, internet_node_added flag.
    """

    def __init__(
        self,
        nodes: List[Dict[str, Any]],
        subnet_prefix: int,
        shared_gateway_nodes: Dict[str, str],
        shared_gateway_devices: Dict[str, List[Any]],
        ip_to_host_id: Dict[str, str],
    ):
        """
        Initialize the GatewayResolver.

        Args:
            nodes: Reference to the nodes list (will be modified to add synthetic gateways)
            subnet_prefix: Subnet prefix for CIDR calculations (e.g., 24 for /24)
            shared_gateway_nodes: Mapping of device_id → gateway_node_id for shared gateways
            shared_gateway_devices: Mapping of device_id → list of host objects for shared gateways
            ip_to_host_id: Mapping of IP address → host ID for lookup
        """
        self.nodes = nodes
        self.subnet_prefix = subnet_prefix
        self.shared_gateway_nodes = shared_gateway_nodes
        self.shared_gateway_devices = shared_gateway_devices
        self.ip_to_host_id = ip_to_host_id
        self.subnet_gateways: Dict[str, str] = {}
        self.internet_node_added = False

    def find_or_create_gateway(
        self, source_subnet_id: str, source_subnet_cidr: str
    ) -> str:
        """
        Find the gateway for a subnet, or create a synthetic one.

        Implements the 4-strategy gateway resolution:
        - Strategy 0: Check if subnet is served by a shared gateway
        - Strategy 1: Look for a router node already in this subnet
        - Strategy 2: Look for a host at .1 address in this subnet
        - Strategy 3: Create a synthetic gateway node

        Args:
            source_subnet_id: Subnet identifier (e.g., "subnet_10.0.0.0/24")
            source_subnet_cidr: Subnet CIDR notation (e.g., "10.0.0.0/24")

        Returns:
            Gateway node ID (string)
        """
        # Return cached result if available
        if source_subnet_id in self.subnet_gateways:
            return self.subnet_gateways[source_subnet_id]

        # Strategy 0: Check if this subnet is served by a shared gateway
        for device_id, shared_gw_id in self.shared_gateway_nodes.items():
            gw_hosts = self.shared_gateway_devices.get(device_id, [])
            gw_subnets = [
                get_subnet(h.ip_address, self.subnet_prefix) for h in gw_hosts
            ]
            if source_subnet_cidr in gw_subnets:
                self.subnet_gateways[source_subnet_id] = shared_gw_id
                return shared_gw_id

        # Strategy 1: Look for a router node already in this subnet
        for n in self.nodes:
            d = n["data"]
            if d.get("parent") == source_subnet_id and d.get("is_gateway"):
                self.subnet_gateways[source_subnet_id] = d["id"]
                return d["id"]

        # Strategy 2: Look for a host at .1 address in this subnet
        try:
            net = ip_network(source_subnet_cidr, strict=False)
            gw_ip = str(net.network_address + DEFAULT_GATEWAY_IP_OFFSET)
            if gw_ip in self.ip_to_host_id:
                gw_id = str(self.ip_to_host_id[gw_ip])
                self.subnet_gateways[source_subnet_id] = gw_id
                return gw_id
        except (ValueError, TypeError):
            pass

        # Strategy 3: Create a synthetic gateway node
        try:
            net = ip_network(source_subnet_cidr, strict=False)
            gw_ip = str(net.network_address + DEFAULT_GATEWAY_IP_OFFSET)
        except (ValueError, TypeError):
            gw_ip = "?.?.?.1"

        gw_node_id = f"gw_{source_subnet_id}"
        self.nodes.append(
            {
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
            }
        )
        self.subnet_gateways[source_subnet_id] = gw_node_id
        return gw_node_id

    def ensure_internet_node(self, nodes: List[Dict[str, Any]]) -> str:
        """
        Add the Internet cloud node if not yet added.

        Args:
            nodes: The nodes list to append the Internet node to

        Returns:
            Internet node ID
        """
        if not self.internet_node_added:
            nodes.append(
                {
                    "data": {
                        "id": INTERNET_NODE_ID,
                        "label": "Internet",
                        "type": "internet",
                        "device_type": "internet",
                        "color": INTERNET_NODE_COLOR,
                        "node_shape": "ellipse",
                        "node_size": 70,
                    }
                }
            )
            self.internet_node_added = True
        return INTERNET_NODE_ID


def build_all_edges(
    connections: List[Any],
    hosts: List[Any],
    nodes: List[Dict[str, Any]],
    ip_to_host_id: Dict[str, str],
    show_internet: str,
    route_through_gateway: bool,
    subnet_prefix: int,
    shared_gateway_nodes: Dict[str, str],
    shared_gateway_devices: Dict[str, List[Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Build all edges from connections with intelligent gateway routing.

    This function processes connections between hosts and creates edges based on:
    - Host-to-host connections in same/different subnets/VLANs
    - Public IP connections (via Internet cloud node)
    - Gateway routing for cross-subnet/cross-VLAN connections

    Args:
        connections: List of Connection objects
        hosts: List of Host objects
        nodes: Mutable list of node dictionaries (will be modified with gateway nodes)
        ip_to_host_id: Mapping of IP address → host ID
        show_internet: One of "hide", "show", "cloud" (how to display public IPs)
        route_through_gateway: Whether to route cross-subnet/cross-VLAN through gateways
        subnet_prefix: Subnet prefix for CIDR calculations (e.g., 24 for /24)
        shared_gateway_nodes: Mapping of device_id → gateway_node_id for shared gateways
        shared_gateway_devices: Mapping of device_id → list of host objects for shared gateways

    Returns:
        Tuple of (edges list, edge_stats_dict) where edge_stats_dict contains:
        - cross_vlan_count: Number of cross-VLAN connections
        - cross_subnet_count: Number of cross-subnet connections
        - internet_conn_count: Number of internet connections
    """
    edges: List[Dict[str, Any]] = []
    edge_set: Set[Tuple[str, str]] = set()

    # Statistics
    cross_vlan_count = 0
    cross_subnet_count = 0
    internet_conn_count = 0

    # Build IP → (vlan, subnet) lookup for edge classification
    ip_context: Dict[str, Dict[str, Any]] = {}
    for host in hosts:
        subnet_cidr_ctx = get_subnet(host.ip_address, subnet_prefix)
        ip_context[host.ip_address] = {
            "vlan_id": host.vlan_id,
            "subnet": subnet_cidr_ctx,
        }

    # Initialize gateway resolver
    resolver = GatewayResolver(
        nodes=nodes,
        subnet_prefix=subnet_prefix,
        shared_gateway_nodes=shared_gateway_nodes,
        shared_gateway_devices=shared_gateway_devices,
        ip_to_host_id=ip_to_host_id,
    )

    # Track gateway → public IPs for tooltip aggregation
    gateway_public_ips: Dict[str, Set[str]] = defaultdict(set)
    gateway_internet_edges: Set[str] = set()

    # Process each connection
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

                # Determine connection type
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

                    gw_from = resolver.find_or_create_gateway(from_subnet_id, from_subnet)
                    gw_to = resolver.find_or_create_gateway(to_subnet_id, to_subnet)

                    # Edge: source host → source gateway
                    hgw_key_from = tuple(sorted([str(from_id), str(gw_from)]))
                    if hgw_key_from not in edge_set:
                        edge_set.add(hgw_key_from)
                        edges.append(
                            {
                                "data": {
                                    "id": f"{from_id}-{gw_from}",
                                    "source": str(from_id),
                                    "target": str(gw_from),
                                    "connection_type": "to_gateway",
                                    "protocol": conn.protocol or "tcp",
                                    "tooltip": f"{conn.local_ip} → gateway ({from_subnet})",
                                }
                            }
                        )

                    # Edge: source gateway → target gateway
                    gw_gw_key = tuple(sorted([str(gw_from), str(gw_to)]))
                    if gw_gw_key not in edge_set:
                        edge_set.add(gw_gw_key)
                        edges.append(
                            {
                                "data": {
                                    "id": f"{gw_from}-{gw_to}",
                                    "source": str(gw_from),
                                    "target": str(gw_to),
                                    "connection_type": conn_type,
                                    "protocol": conn.protocol or "tcp",
                                    "tooltip": f"Gateway {from_subnet} → Gateway {to_subnet}",
                                }
                            }
                        )

                    # Edge: target gateway → target host
                    hgw_key_to = tuple(sorted([str(to_id), str(gw_to)]))
                    if hgw_key_to not in edge_set:
                        edge_set.add(hgw_key_to)
                        edges.append(
                            {
                                "data": {
                                    "id": f"{gw_to}-{to_id}",
                                    "source": str(gw_to),
                                    "target": str(to_id),
                                    "connection_type": "to_gateway",
                                    "protocol": conn.protocol or "tcp",
                                    "tooltip": f"gateway ({to_subnet}) → {conn.remote_ip}",
                                }
                            }
                        )
                else:
                    # Direct edge (same subnet or route_through_gateway disabled)
                    edge = {
                        "data": {
                            "id": f"{from_id}-{to_id}",
                            "source": str(from_id),
                            "target": str(to_id),
                            "connection_type": conn_type,
                            "protocol": conn.protocol or "tcp",
                            "port_info": f"{conn.local_port} → {conn.remote_port}"
                            if conn.remote_port
                            else str(conn.local_port),
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
            gw_id = resolver.find_or_create_gateway(source_subnet_id, source_subnet_cidr)

            # Edge: local host → gateway (if not already connected)
            host_gw_key = tuple(sorted([str(source_host_id), str(gw_id)]))
            if host_gw_key not in edge_set:
                edge_set.add(host_gw_key)
                edges.append(
                    {
                        "data": {
                            "id": f"{source_host_id}-{gw_id}",
                            "source": str(source_host_id),
                            "target": str(gw_id),
                            "connection_type": "to_gateway",
                            "protocol": conn.protocol or "tcp",
                            "tooltip": f"{local_ip} → gateway (→ {remote_ip}:{conn.remote_port or '?'})",
                        }
                    }
                )

            # Track which public IPs go through this gateway
            gateway_public_ips[gw_id].add(remote_ip)

            # Ensure Internet node exists + create gateway→Internet edge (once per gateway)
            resolver.ensure_internet_node(nodes)
            if gw_id not in gateway_internet_edges:
                gateway_internet_edges.add(gw_id)
                edges.append(
                    {
                        "data": {
                            "id": f"{gw_id}-{INTERNET_NODE_ID}",
                            "source": str(gw_id),
                            "target": INTERNET_NODE_ID,
                            "connection_type": "internet",
                            "tooltip": "Gateway → Internet",
                        }
                    }
                )

    # Update gateway→Internet edge tooltips with public IP counts
    for edge in edges:
        d = edge["data"]
        if d.get("connection_type") == "internet":
            gw = d["source"]
            pub_ips = gateway_public_ips.get(gw, set())
            count = len(pub_ips)
            sample = sorted(pub_ips)[:MAX_PUBLIC_IP_SAMPLES]
            sample_str = ", ".join(sample)
            if count > MAX_PUBLIC_IP_SAMPLES:
                sample_str += f" (+{count - MAX_PUBLIC_IP_SAMPLES} more)"
            d["tooltip"] = f"Gateway → Internet ({count} ext. IPs)\n{sample_str}"
            d["public_ip_count"] = count

    # Return edges and statistics
    edge_stats = {
        "cross_vlan_count": cross_vlan_count,
        "cross_subnet_count": cross_subnet_count,
        "internet_conn_count": internet_conn_count,
    }

    return edges, edge_stats

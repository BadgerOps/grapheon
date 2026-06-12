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
from network.validators import is_private_ip, get_observed_subnet


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
        observed_networks: list | None = None,
    ):
        """
        Initialize the GatewayResolver.

        Args:
            nodes: Reference to the nodes list (will be modified to add synthetic gateways)
            subnet_prefix: Optional fallback prefix for CIDR calculations
            shared_gateway_nodes: Mapping of device_id → gateway_node_id for shared gateways
            shared_gateway_devices: Mapping of device_id → list of host objects for shared gateways
            ip_to_host_id: Mapping of IP address → host ID for lookup
        """
        self.nodes = nodes
        self.subnet_prefix = subnet_prefix
        self.shared_gateway_nodes = shared_gateway_nodes
        self.shared_gateway_devices = shared_gateway_devices
        self.ip_to_host_id = ip_to_host_id
        self.observed_networks = observed_networks or []
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
                get_observed_subnet(h.ip_address, self.subnet_prefix, self.observed_networks)
                for h in gw_hosts
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
    observed_networks: list | None = None,
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
        subnet_prefix: Optional fallback prefix for CIDR calculations
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
    observed_networks = observed_networks or []

    # Build IP → (vlan, subnet) lookup for edge classification
    ip_context: Dict[str, Dict[str, Any]] = {}
    for host in hosts:
        subnet_cidr_ctx = get_observed_subnet(host.ip_address, subnet_prefix, observed_networks)
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
        observed_networks=observed_networks,
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


def add_agent_topology_edges(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    observations: List[Any],
    agents_by_id: Dict[int, Any],
    ip_to_host_id: Dict[str, str],
    include_collector_nodes: bool,
) -> Dict[str, int]:
    """
    Add agent-vantage relationship edges derived from current observations.

    Existing connection edges answer "what endpoints communicated"; these edges
    answer "which collector observed what, and from which local vantage point".
    """
    edge_ids = {edge["data"]["id"] for edge in edges}
    added_counts = {
        "collector_interface": 0,
        "arp_neighbor": 0,
        "connection_remote": 0,
        "route_gateway": 0,
        "l2_neighbor": 0,
        "switch_port_attachment": 0,
        "mac_ip_binding": 0,
        "dhcp_lease": 0,
        "dns_name": 0,
        "route": 0,
        "flow_relationship": 0,
        "network_segment": 0,
    }
    node_ids = {node["data"].get("id") for node in nodes}

    address_by_agent_interface: Dict[tuple[int, str], str] = {}
    first_address_by_agent: Dict[int, str] = {}
    for observation in observations:
        if observation.observation_type != "address" or not observation.is_current:
            continue
        payload = observation.payload or {}
        ip_address = payload.get("ip_address")
        interface = payload.get("interface")
        if not ip_address:
            continue
        if observation.agent_id not in first_address_by_agent:
            first_address_by_agent[observation.agent_id] = ip_address
        if interface:
            address_by_agent_interface[(observation.agent_id, interface)] = ip_address

    collector_node_ids: set[str] = set()
    if include_collector_nodes:
        for agent_id in sorted({observation.agent_id for observation in observations}):
            agent = agents_by_id.get(agent_id)
            if not agent:
                continue
            node_id = f"agent_{agent_id}"
            collector_node_ids.add(node_id)
            if any(node["data"].get("id") == node_id for node in nodes):
                continue
            label = agent.display_name or agent.hostname or agent.agent_uuid
            nodes.append(
                {
                    "data": {
                        "id": node_id,
                        "label": f"Collector\n{label}",
                        "type": "agent_collector",
                        "device_type": "collector",
                        "agent_id": agent_id,
                        "agent_uuid": agent.agent_uuid,
                        "hostname": agent.hostname,
                        "node_shape": "hexagon",
                        "node_size": 58,
                        "color": "#14b8a6",
                        "tooltip": (
                            f"<b>Agent Collector</b><br>{label}"
                            f"<br>agent_id={agent_id}"
                        ),
                    }
                }
            )

    def add_edge(
        source: str,
        target: str,
        observation: Any,
        connection_type: str,
        tooltip: str,
    ) -> None:
        if not source or not target or source == target:
            return
        edge_id = f"agent_{observation.id}_{connection_type}_{source}_{target}"
        if edge_id in edge_ids:
            return
        edge_ids.add(edge_id)
        edges.append(
            {
                "data": {
                    "id": edge_id,
                    "source": str(source),
                    "target": str(target),
                    "connection_type": connection_type,
                    "relationship_type": observation.relationship_type,
                    "observation_role": observation.observation_role,
                    "confidence": observation.confidence,
                    "source_origin": "agent",
                    "observer_agent_id": observation.agent_id,
                    "agent_id": observation.agent_id,
                    "agent_observation_id": observation.id,
                    "raw_import_id": observation.raw_import_id,
                    "first_seen_at": observation.first_seen_at.isoformat()
                    if observation.first_seen_at
                    else None,
                    "last_seen_at": observation.last_seen_at.isoformat()
                    if observation.last_seen_at
                    else None,
                    "relationship_key": observation.relationship_key,
                    "topology_evidence": [
                        {
                            "source": (observation.payload or {}).get("source") or "agent",
                            "observer": (observation.payload or {}).get("observer"),
                            "confidence": observation.confidence,
                            "first_seen": observation.first_seen_at.isoformat()
                            if observation.first_seen_at
                            else None,
                            "last_seen": observation.last_seen_at.isoformat()
                            if observation.last_seen_at
                            else None,
                            "evidence_type": observation.relationship_type,
                            "summary": _topology_edge_summary(observation.payload or {}),
                            "raw_ref": (observation.payload or {}).get("raw_ref"),
                        }
                    ],
                    "tooltip": tooltip,
                }
            }
        )
        if connection_type in added_counts:
            added_counts[connection_type] += 1

    def ensure_evidence_node(
        node_id: str,
        label: str,
        node_type: str,
        observation: Any,
        *,
        color: str = "#64748b",
        shape: str = "round-rectangle",
    ) -> str:
        if node_id in node_ids:
            return node_id
        payload = observation.payload or {}
        node_ids.add(node_id)
        nodes.append(
            {
                "data": {
                    "id": node_id,
                    "label": label,
                    "type": node_type,
                    "device_type": node_type,
                    "node_shape": shape,
                    "node_size": 42,
                    "color": color,
                    "relationship_type": observation.relationship_type,
                    "source_origin": "agent",
                    "source_type": payload.get("source") or "agent",
                    "observer_agent_id": observation.agent_id,
                    "agent_observation_id": observation.id,
                    "topology_evidence": [
                        {
                            "source": payload.get("source") or "agent",
                            "observer": payload.get("observer"),
                            "confidence": observation.confidence,
                            "first_seen": observation.first_seen_at.isoformat()
                            if observation.first_seen_at
                            else None,
                            "last_seen": observation.last_seen_at.isoformat()
                            if observation.last_seen_at
                            else None,
                            "evidence_type": observation.relationship_type,
                            "summary": _topology_edge_summary(payload),
                            "raw_ref": payload.get("raw_ref"),
                        }
                    ],
                    "tooltip": tooltip_from_payload(payload, label),
                }
            }
        )
        return node_id

    for observation in observations:
        payload = observation.payload or {}
        relationship_type = observation.relationship_type
        if relationship_type == "collector_interface":
            collector_id = f"agent_{observation.agent_id}"
            host_id = ip_to_host_id.get(payload.get("ip_address"))
            if include_collector_nodes and collector_id in collector_node_ids and host_id:
                add_edge(
                    collector_id,
                    str(host_id),
                    observation,
                    "collector_interface",
                    (
                        f"Collector observed local interface "
                        f"{payload.get('ip_address')} ({observation.confidence}% confidence)"
                    ),
                )
            continue

        if relationship_type == "arp_neighbor":
            interface = payload.get("interface")
            local_ip = address_by_agent_interface.get((observation.agent_id, interface))
            source_id = ip_to_host_id.get(local_ip) if local_ip else None
            target_id = ip_to_host_id.get(payload.get("ip_address"))
            if source_id and target_id:
                add_edge(
                    str(source_id),
                    str(target_id),
                    observation,
                    "arp_neighbor",
                    (
                        f"ARP neighbor via {interface or 'unknown interface'}: "
                        f"{local_ip or '?'} -> {payload.get('ip_address')}"
                    ),
                )
            continue

        if relationship_type == "connection_remote":
            source_id = ip_to_host_id.get(payload.get("local_ip"))
            target_id = ip_to_host_id.get(payload.get("remote_ip"))
            if source_id and target_id:
                add_edge(
                    str(source_id),
                    str(target_id),
                    observation,
                    "connection_remote",
                    (
                        f"Observed connection {payload.get('local_ip')}:"
                        f"{payload.get('local_port')} -> {payload.get('remote_ip')}:"
                        f"{payload.get('remote_port') or '?'}"
                    ),
                )
            continue

        if relationship_type == "route_gateway":
            source_ip = payload.get("source_ip")
            if not source_ip and payload.get("interface"):
                source_ip = address_by_agent_interface.get(
                    (observation.agent_id, payload.get("interface"))
                )
            if not source_ip:
                source_ip = first_address_by_agent.get(observation.agent_id)
            source_id = ip_to_host_id.get(source_ip)
            target_id = ip_to_host_id.get(payload.get("gateway"))
            if source_id and target_id:
                add_edge(
                    str(source_id),
                    str(target_id),
                    observation,
                    "route_gateway",
                    (
                        f"Route to {payload.get('destination')} via "
                        f"{payload.get('gateway')} ({observation.confidence}% confidence)"
                    ),
                )
            continue

        if relationship_type == "flow_relationship":
            source_id = ip_to_host_id.get(payload.get("local_ip"))
            target_id = ip_to_host_id.get(payload.get("remote_ip"))
            if source_id and target_id:
                add_edge(
                    str(source_id),
                    str(target_id),
                    observation,
                    "flow_relationship",
                    _topology_edge_summary(payload),
                )
            continue

        if relationship_type == "route":
            source_id = ip_to_host_id.get(payload.get("source_ip"))
            target_id = ip_to_host_id.get(payload.get("gateway"))
            if source_id and target_id:
                add_edge(
                    str(source_id),
                    str(target_id),
                    observation,
                    "route",
                    _topology_edge_summary(payload),
                )
            continue

        if relationship_type in {"mac_ip_binding", "dhcp_lease"}:
            host_id = ip_to_host_id.get(payload.get("ip_address"))
            if host_id and payload.get("mac_address"):
                mac_node = ensure_evidence_node(
                    f"mac_{payload.get('mac_address')}",
                    f"MAC\n{payload.get('mac_address')}",
                    "mac_identity",
                    observation,
                    color="#0f766e",
                )
                add_edge(mac_node, str(host_id), observation, relationship_type, _topology_edge_summary(payload))
            continue

        if relationship_type == "dns_name":
            host_id = ip_to_host_id.get(payload.get("ip_address"))
            dns_name = payload.get("name") or payload.get("hostname") or payload.get("fqdn")
            if host_id and dns_name:
                dns_node = ensure_evidence_node(
                    f"dns_{dns_name}",
                    f"DNS\n{dns_name}",
                    "dns_name",
                    observation,
                    color="#2563eb",
                )
                add_edge(str(host_id), dns_node, observation, "dns_name", _topology_edge_summary(payload))
            continue

        if relationship_type == "network_segment":
            network = payload.get("network")
            host_id = ip_to_host_id.get(payload.get("ip_address"))
            if network:
                segment_node = ensure_evidence_node(
                    f"segment_{network}",
                    f"Segment\n{network}",
                    "network_segment",
                    observation,
                    color="#7c3aed",
                )
                if host_id:
                    add_edge(str(host_id), segment_node, observation, "network_segment", _topology_edge_summary(payload))
            continue

        if relationship_type == "l2_neighbor":
            local_ip = address_by_agent_interface.get(
                (observation.agent_id, payload.get("interface"))
            ) or first_address_by_agent.get(observation.agent_id)
            source_id = ip_to_host_id.get(local_ip)
            target_id = ip_to_host_id.get(payload.get("management_ip") or payload.get("switch_ip"))
            if not target_id and (payload.get("system_name") or payload.get("chassis_id")):
                target_id = ensure_evidence_node(
                    f"l2_{payload.get('chassis_id') or payload.get('system_name')}",
                    f"L2\n{payload.get('system_name') or payload.get('chassis_id')}",
                    "l2_neighbor",
                    observation,
                    color="#0891b2",
                    shape="hexagon",
                )
            if source_id and target_id:
                add_edge(str(source_id), str(target_id), observation, "l2_neighbor", _topology_edge_summary(payload))
            continue

        if relationship_type == "switch_port_attachment":
            host_id = ip_to_host_id.get(payload.get("ip_address"))
            switch_id = ip_to_host_id.get(payload.get("switch_ip") or payload.get("management_ip"))
            port_label = payload.get("switch_port") or payload.get("port_id") or "port"
            if switch_id:
                port_node = ensure_evidence_node(
                    f"switch_port_{switch_id}_{port_label}",
                    f"Port\n{port_label}",
                    "switch_port",
                    observation,
                    color="#9333ea",
                )
                add_edge(str(switch_id), port_node, observation, "switch_port_attachment", _topology_edge_summary(payload))
                if host_id:
                    add_edge(str(host_id), port_node, observation, "switch_port_attachment", _topology_edge_summary(payload))

    return added_counts


def _topology_edge_summary(payload: dict[str, Any]) -> str:
    evidence_type = payload.get("evidence_type") or "topology_evidence"
    if evidence_type == "flow_relationship":
        return (
            f"{payload.get('local_ip') or '?'}:{payload.get('local_port') or '?'} -> "
            f"{payload.get('remote_ip') or '?'}:{payload.get('remote_port') or '?'}"
        )
    if evidence_type in {"route", "route_gateway"}:
        return f"{payload.get('source_ip') or '?'} -> {payload.get('destination') or '?'} via {payload.get('gateway') or '?'}"
    if evidence_type == "dns_name":
        return f"{payload.get('ip_address') or '?'} -> {payload.get('name') or payload.get('hostname') or '?'}"
    if evidence_type == "network_segment":
        return f"{payload.get('network') or '?'} vlan={payload.get('vlan_id') or '?'}"
    if evidence_type == "switch_port_attachment":
        return (
            f"{payload.get('mac_address') or payload.get('ip_address') or '?'} on "
            f"{payload.get('switch_name') or payload.get('switch_ip') or '?'} "
            f"{payload.get('switch_port') or payload.get('port_id') or '?'}"
        )
    if evidence_type == "l2_neighbor":
        return f"{payload.get('system_name') or payload.get('chassis_id') or '?'} port {payload.get('port_id') or '?'}"
    if evidence_type in {"mac_ip_binding", "dhcp_lease"}:
        return f"{payload.get('mac_address') or '?'} -> {payload.get('ip_address') or '?'}"
    return evidence_type


def tooltip_from_payload(payload: dict[str, Any], label: str) -> str:
    return f"{label}<br>{_topology_edge_summary(payload)}"

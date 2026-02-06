"""
Node styling, tooltips, and color assignment for network visualization.
"""
from network.constants import DEVICE_STYLES, DEFAULT_STYLE, VLAN_COLORS, SUBNET_COLORS


def get_device_style(device_type: str | None) -> dict:
    """Get Cytoscape node styling dict for a device type string."""
    if device_type:
        return DEVICE_STYLES.get(device_type.lower(), DEFAULT_STYLE)
    return DEFAULT_STYLE


def build_node_tooltip(host, open_ports: int) -> str:
    """Build HTML tooltip for a host node."""
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


def get_vlan_color(vlan_id: int, config_color: str = None) -> str:
    """Get color for a VLAN — use configured color or auto-assign."""
    if config_color:
        return config_color
    return VLAN_COLORS[vlan_id % len(VLAN_COLORS)]


def get_subnet_color(subnet: str) -> str:
    """Generate a consistent color for a subnet string."""
    hash_val = sum(ord(c) for c in subnet)
    return SUBNET_COLORS[hash_val % len(SUBNET_COLORS)]

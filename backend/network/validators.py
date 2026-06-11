"""
IP address and subnet validation utilities.
"""
from typing import Optional
from ipaddress import ip_address, ip_network

from network.constants import PRIVATE_NETWORKS


def is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private/non-routable (RFC1918, loopback, link-local, CGNAT)."""
    try:
        addr = ip_address(ip_str)
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


def get_observed_subnet(
    ip: str,
    prefix: Optional[int] = None,
    observed_networks=None,
) -> str:
    """Resolve a host subnet from observed agent networks, falling back to prefix."""
    try:
        addr = ip_address(ip)
    except Exception:
        return "unknown/0"

    if observed_networks:
        matching_networks = [
            network for network in observed_networks if addr.version == network.version and addr in network
        ]
        if matching_networks:
            return str(max(matching_networks, key=lambda network: network.prefixlen))

    if prefix is not None:
        return get_subnet(ip, prefix)
    return f"unresolved-ipv{addr.version}"

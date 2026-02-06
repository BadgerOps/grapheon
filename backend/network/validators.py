"""
IP address and subnet validation utilities.
"""
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

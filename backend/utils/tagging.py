"""Tag derivation helpers for parsed network data."""

from __future__ import annotations

import re
from ipaddress import ip_address, ip_network
from typing import Iterable, Optional, List, Set


def _normalize(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"\s+", "_", value)
    return value


def _add_tag(tags: Set[str], key: str, value: Optional[str]) -> None:
    if not value:
        return
    tags.add(f"{key}:{_normalize(str(value))}")


def _derive_subnet_tag(value: Optional[str], v4_prefix: int = 24, v6_prefix: int = 64) -> Optional[str]:
    if not value:
        return None
    try:
        addr = ip_address(value)
    except ValueError:
        return None

    prefix = v4_prefix if addr.version == 4 else v6_prefix
    network = ip_network(f"{value}/{prefix}", strict=False)
    return f"{network.network_address}/{prefix}"


def merge_tags(existing: Optional[List[str]], new_tags: Iterable[str]) -> List[str]:
    """Merge new tags into existing tag list, ensuring uniqueness."""
    merged = set(t for t in (existing or []) if t)
    merged.update(t for t in new_tags if t)
    return sorted(merged)


def build_host_tags(
    ip_address: Optional[str] = None,
    mac_address: Optional[str] = None,
    hostname: Optional[str] = None,
    fqdn: Optional[str] = None,
    vendor: Optional[str] = None,
    os_family: Optional[str] = None,
    os_name: Optional[str] = None,
) -> List[str]:
    tags: Set[str] = set()
    _add_tag(tags, "ip", ip_address)
    _add_tag(tags, "subnet", _derive_subnet_tag(ip_address))
    _add_tag(tags, "mac", mac_address)
    _add_tag(tags, "hostname", hostname)
    _add_tag(tags, "fqdn", fqdn)
    _add_tag(tags, "vendor", vendor)
    _add_tag(tags, "os_family", os_family)
    _add_tag(tags, "os", os_name)
    return sorted(tags)


def build_port_tags(
    port_number: Optional[int] = None,
    protocol: Optional[str] = None,
    state: Optional[str] = None,
    service_name: Optional[str] = None,
    service_product: Optional[str] = None,
    service_version: Optional[str] = None,
) -> List[str]:
    tags: Set[str] = set()
    if port_number is not None:
        _add_tag(tags, "port", str(port_number))
    if port_number is not None and protocol:
        _add_tag(tags, "port_proto", f"{port_number}/{protocol}")
    _add_tag(tags, "protocol", protocol)
    _add_tag(tags, "state", state)
    _add_tag(tags, "service", service_name)
    _add_tag(tags, "product", service_product)
    _add_tag(tags, "version", service_version)
    return sorted(tags)


def build_connection_tags(
    local_ip: Optional[str] = None,
    local_port: Optional[int] = None,
    remote_ip: Optional[str] = None,
    remote_port: Optional[int] = None,
    protocol: Optional[str] = None,
    state: Optional[str] = None,
    process_name: Optional[str] = None,
) -> List[str]:
    tags: Set[str] = set()
    _add_tag(tags, "local_ip", local_ip)
    if local_port is not None:
        _add_tag(tags, "local_port", str(local_port))
    _add_tag(tags, "local_subnet", _derive_subnet_tag(local_ip))
    _add_tag(tags, "remote_ip", remote_ip)
    if remote_port is not None:
        _add_tag(tags, "remote_port", str(remote_port))
    _add_tag(tags, "remote_subnet", _derive_subnet_tag(remote_ip))
    _add_tag(tags, "protocol", protocol)
    _add_tag(tags, "state", state)
    _add_tag(tags, "process", process_name)
    return sorted(tags)


def build_arp_tags(
    ip_address: Optional[str] = None,
    mac_address: Optional[str] = None,
    interface: Optional[str] = None,
    entry_type: Optional[str] = None,
    vendor: Optional[str] = None,
) -> List[str]:
    tags: Set[str] = set()
    _add_tag(tags, "ip", ip_address)
    _add_tag(tags, "subnet", _derive_subnet_tag(ip_address))
    _add_tag(tags, "mac", mac_address)
    _add_tag(tags, "interface", interface)
    _add_tag(tags, "entry_type", entry_type)
    _add_tag(tags, "vendor", vendor)
    return sorted(tags)

"""Base classes and data structures for network data parsing."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class ParsedHost:
    """Represents a parsed host from any source."""

    ip_address: str
    mac_address: Optional[str] = None
    hostname: Optional[str] = None
    fqdn: Optional[str] = None
    vendor: Optional[str] = None
    os_name: Optional[str] = None
    os_version: Optional[str] = None
    os_family: Optional[str] = None  # linux/windows/macos/network/unknown
    os_confidence: Optional[int] = None
    device_type: Optional[str] = None
    ports: List["ParsedPort"] = field(default_factory=list)


@dataclass
class ParsedPort:
    """Represents a parsed port."""

    port_number: int
    protocol: str  # tcp/udp
    state: str  # open/closed/filtered
    service_name: Optional[str] = None
    service_version: Optional[str] = None
    service_product: Optional[str] = None
    service_banner: Optional[str] = None
    confidence: Optional[int] = None


@dataclass
class ParsedConnection:
    """Represents a parsed connection from netstat."""

    local_ip: str
    local_port: int
    remote_ip: str
    remote_port: int
    protocol: str
    state: str
    pid: Optional[int] = None
    process_name: Optional[str] = None


@dataclass
class ParsedArpEntry:
    """Represents a parsed ARP entry."""

    ip_address: str
    mac_address: str
    interface: Optional[str] = None
    entry_type: Optional[str] = None  # dynamic/static/permanent
    vendor: Optional[str] = None


@dataclass
class ParsedRouteHop:
    """Represents a single hop in a traceroute."""

    hop_number: int
    ip_address: Optional[str] = None
    hostname: Optional[str] = None
    rtt_ms: List[float] = field(default_factory=list)  # Usually 3 samples


@dataclass
class ParseResult:
    """Result of parsing operation."""

    success: bool
    source_type: str
    hosts: List[ParsedHost] = field(default_factory=list)
    connections: List[ParsedConnection] = field(default_factory=list)
    arp_entries: List[ParsedArpEntry] = field(default_factory=list)
    route_hops: List[ParsedRouteHop] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    parsed_at: datetime = field(default_factory=datetime.utcnow)


class BaseParser(ABC):
    """Abstract base class for all parsers."""

    source_type: str = "unknown"

    @abstractmethod
    def parse(self, data: str, **kwargs) -> ParseResult:
        """Parse input data and return structured result."""
        pass

    def detect_format(self, data: str) -> Optional[str]:
        """Detect the format of input data. Override in subclasses."""
        return None

    def _infer_os_family(self, os_string: str) -> str:
        """Infer OS family from OS string."""
        if not os_string:
            return "unknown"
        os_lower = os_string.lower()
        if any(
            x in os_lower
            for x in [
                "linux",
                "ubuntu",
                "debian",
                "centos",
                "rhel",
                "fedora",
                "arch",
                "alpine",
            ]
        ):
            return "linux"
        if any(x in os_lower for x in ["windows", "microsoft", "win32"]):
            return "windows"
        if any(x in os_lower for x in ["mac", "darwin", "osx", "os x", "macos"]):
            return "macos"
        if any(
            x in os_lower
            for x in [
                "ios",
                "cisco",
                "juniper",
                "router",
                "switch",
                "firewall",
                "pfsense",
                "vyos",
            ]
        ):
            return "network"
        return "unknown"

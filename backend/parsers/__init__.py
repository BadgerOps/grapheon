"""Parser package for network data aggregation.

This package contains parsers for various network scanning and discovery tools.
"""

from .base import (
    BaseParser,
    ParsedHost,
    ParsedPort,
    ParsedConnection,
    ParsedArpEntry,
    ParsedRouteHop,
    ParseResult,
)
from .nmap import NmapParser
from .netstat import NetstatParser
from .arp import ArpParser
from .traceroute import TracerouteParser
from .ping import PingParser
from .pcap import PcapParser

# Parser registry mapping tool names to parser classes
PARSERS = {
    "nmap": NmapParser,
    "netstat": NetstatParser,
    "arp": ArpParser,
    "traceroute": TracerouteParser,
    "ping": PingParser,
    "pcap": PcapParser,
    "tcpdump": PcapParser,  # Alias for tcpdump text output
}


def get_parser(tool_name: str) -> BaseParser:
    """Get a parser instance by tool name.

    Args:
        tool_name: Name of the tool (e.g., 'nmap', 'arp')

    Returns:
        Parser instance

    Raises:
        ValueError: If tool_name is not registered
    """
    parser_class = PARSERS.get(tool_name.lower())
    if parser_class is None:
        raise ValueError(
            f"Unknown parser: {tool_name}. Available: {', '.join(PARSERS.keys())}"
        )
    return parser_class()


__all__ = [
    "BaseParser",
    "ParsedHost",
    "ParsedPort",
    "ParsedConnection",
    "ParsedArpEntry",
    "ParsedRouteHop",
    "ParseResult",
    "NmapParser",
    "NetstatParser",
    "ArpParser",
    "TracerouteParser",
    "PingParser",
    "PARSERS",
    "get_parser",
]

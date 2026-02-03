"""
PCAP parser for extracting network connection flows.

Parses packet capture files to extract:
- TCP/UDP connection flows (src/dst IP and port)
- Protocol identification
- Connection timestamps
- Packet/byte counts per flow

Requires: scapy (pip install scapy)
"""

import importlib.util
import logging
from datetime import datetime
from typing import Optional, Dict, Set, Tuple
from collections import defaultdict
from dataclasses import dataclass, field

from .base import BaseParser, ParseResult, ParsedHost, ParsedPort, ParsedConnection

logger = logging.getLogger(__name__)


@dataclass
class FlowKey:
    """Unique identifier for a network flow."""
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    protocol: str  # tcp, udp, icmp

    def __hash__(self):
        return hash((self.src_ip, self.src_port, self.dst_ip, self.dst_port, self.protocol))

    def __eq__(self, other):
        return (
            self.src_ip == other.src_ip and
            self.src_port == other.src_port and
            self.dst_ip == other.dst_ip and
            self.dst_port == other.dst_port and
            self.protocol == other.protocol
        )


@dataclass
class FlowStats:
    """Statistics for a network flow."""
    packet_count: int = 0
    byte_count: int = 0
    first_seen: datetime = None
    last_seen: datetime = None
    tcp_flags: Set[str] = field(default_factory=set)


class PcapParser(BaseParser):
    """
    Parser for PCAP/PCAPNG packet capture files.

    Extracts connection flows and host information from packet captures.
    """

    def __init__(self):
        self.source_type = "pcap"
        self._scapy_available = None

    def _check_scapy(self) -> bool:
        """Check if scapy is available."""
        if self._scapy_available is None:
            self._scapy_available = importlib.util.find_spec("scapy.all") is not None
            if not self._scapy_available:
                logger.warning("scapy not available - PCAP parsing will use fallback method")
        return self._scapy_available

    def detect_format(self, data: bytes) -> Optional[str]:
        """
        Detect if data is a PCAP file.

        Args:
            data: Raw file bytes

        Returns:
            "pcap", "pcapng", or None
        """
        if len(data) < 4:
            return None

        # PCAP magic numbers
        magic = data[:4]
        if magic in (b'\xd4\xc3\xb2\xa1', b'\xa1\xb2\xc3\xd4'):  # Little/big endian
            return "pcap"
        if magic in (b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d'):  # Nanosecond resolution
            return "pcap"
        if magic == b'\x0a\x0d\x0d\x0a':  # PCAPNG
            return "pcapng"

        return None

    def parse(self, data: str, format_hint: Optional[str] = None) -> ParseResult:
        """
        Parse PCAP data and extract connection flows.

        Note: This method expects a file path, not raw data, due to binary nature of PCAP.

        Args:
            data: Path to PCAP file
            format_hint: Optional format hint

        Returns:
            ParseResult with hosts and connections
        """
        logger.info(f"PCAP PARSER: Starting parse of {data}")

        result = ParseResult(
            success=False,
            source_type=self.source_type,
            hosts=[],
            connections=[],
            arp_entries=[],
            route_hops=[],
            errors=[],
            warnings=[],
            parsed_at=datetime.utcnow(),
        )

        if not self._check_scapy():
            # Fallback: try to parse as text-based tcpdump output
            return self._parse_tcpdump_text(data, result)

        try:
            from scapy.all import rdpcap, IP, IPv6, TCP, UDP, ICMP

            # Read packets
            logger.info("Loading PCAP file with scapy...")
            packets = rdpcap(data)
            logger.info(f"Loaded {len(packets)} packets")

            # Track flows
            flows: Dict[FlowKey, FlowStats] = defaultdict(FlowStats)
            hosts: Set[str] = set()
            host_ports: Dict[str, Set[Tuple[int, str]]] = defaultdict(set)

            for pkt in packets:
                timestamp = datetime.fromtimestamp(float(pkt.time))

                # Get IP layer
                if IP in pkt:
                    ip_layer = pkt[IP]
                    src_ip = ip_layer.src
                    dst_ip = ip_layer.dst
                elif IPv6 in pkt:
                    ip_layer = pkt[IPv6]
                    src_ip = ip_layer.src
                    dst_ip = ip_layer.dst
                else:
                    continue

                hosts.add(src_ip)
                hosts.add(dst_ip)

                # Get transport layer
                if TCP in pkt:
                    tcp = pkt[TCP]
                    src_port = tcp.sport
                    dst_port = tcp.dport
                    protocol = "tcp"

                    # Track TCP flags
                    flow_key = FlowKey(src_ip, src_port, dst_ip, dst_port, protocol)
                    if tcp.flags.S:
                        flows[flow_key].tcp_flags.add("SYN")
                    if tcp.flags.A:
                        flows[flow_key].tcp_flags.add("ACK")
                    if tcp.flags.F:
                        flows[flow_key].tcp_flags.add("FIN")
                    if tcp.flags.R:
                        flows[flow_key].tcp_flags.add("RST")

                elif UDP in pkt:
                    udp = pkt[UDP]
                    src_port = udp.sport
                    dst_port = udp.dport
                    protocol = "udp"
                    flow_key = FlowKey(src_ip, src_port, dst_ip, dst_port, protocol)

                elif ICMP in pkt:
                    src_port = 0
                    dst_port = 0
                    protocol = "icmp"
                    flow_key = FlowKey(src_ip, 0, dst_ip, 0, protocol)

                else:
                    continue

                # Update flow stats
                flow = flows[flow_key]
                flow.packet_count += 1
                flow.byte_count += len(pkt)
                if flow.first_seen is None:
                    flow.first_seen = timestamp
                flow.last_seen = timestamp

                # Track ports per host
                if protocol in ("tcp", "udp"):
                    host_ports[src_ip].add((src_port, protocol))
                    host_ports[dst_ip].add((dst_port, protocol))

            # Convert to ParsedHosts
            for ip in hosts:
                ports = []
                for port_num, proto in host_ports.get(ip, []):
                    if port_num > 0 and port_num < 65536:
                        ports.append(ParsedPort(
                            port_number=port_num,
                            protocol=proto,
                            state="open",  # Seen in traffic = open
                        ))

                result.hosts.append(ParsedHost(
                    ip_address=ip,
                    ports=ports,
                ))

            # Convert to ParsedConnections
            for flow_key, stats in flows.items():
                # Determine connection state based on TCP flags
                state = "ESTABLISHED"
                if "SYN" in stats.tcp_flags and "ACK" not in stats.tcp_flags:
                    state = "SYN_SENT"
                elif "FIN" in stats.tcp_flags or "RST" in stats.tcp_flags:
                    state = "CLOSED"

                result.connections.append(ParsedConnection(
                    local_ip=flow_key.src_ip,
                    local_port=flow_key.src_port,
                    remote_ip=flow_key.dst_ip,
                    remote_port=flow_key.dst_port,
                    protocol=flow_key.protocol,
                    state=state,
                ))

            result.success = True
            logger.info(f"PCAP parse complete: {len(result.hosts)} hosts, {len(result.connections)} flows")

        except FileNotFoundError:
            result.errors.append(f"PCAP file not found: {data}")
            logger.error(f"PCAP file not found: {data}")
        except Exception as e:
            result.errors.append(f"Error parsing PCAP: {str(e)}")
            logger.exception(f"Error parsing PCAP: {e}")

        return result

    def _parse_tcpdump_text(self, data: str, result: ParseResult) -> ParseResult:
        """
        Fallback parser for tcpdump text output.

        Handles output like:
        10:30:45.123456 IP 192.168.1.100.443 > 10.0.0.1.54321: Flags [S], ...
        """
        logger.info("Using tcpdump text fallback parser")

        import re

        # Pattern for tcpdump output
        # Matches: timestamp IP src.port > dst.port: ...
        pattern = r'(\d+:\d+:\d+\.\d+)\s+IP6?\s+(\S+)\.(\d+)\s+>\s+(\S+)\.(\d+):\s+(\w+)'

        hosts: Set[str] = set()
        connections: Dict[Tuple, dict] = {}

        lines = data.strip().split('\n')
        for line in lines:
            match = re.search(pattern, line)
            if match:
                timestamp_str, src_ip, src_port, dst_ip, dst_port, proto_info = match.groups()

                # Clean up IPs (remove trailing dots if any)
                src_ip = src_ip.rstrip('.')
                dst_ip = dst_ip.rstrip('.')

                hosts.add(src_ip)
                hosts.add(dst_ip)

                # Determine protocol
                protocol = "tcp"
                if "UDP" in line.upper():
                    protocol = "udp"

                # Track connection
                conn_key = (src_ip, int(src_port), dst_ip, int(dst_port), protocol)
                if conn_key not in connections:
                    connections[conn_key] = {
                        "count": 0,
                        "state": "ESTABLISHED",
                    }
                connections[conn_key]["count"] += 1

                # Check for TCP flags
                if "Flags [S]" in line and "Flags [S.]" not in line:
                    connections[conn_key]["state"] = "SYN_SENT"
                elif "Flags [F" in line or "Flags [R" in line:
                    connections[conn_key]["state"] = "CLOSED"

        # Convert to results
        for ip in hosts:
            result.hosts.append(ParsedHost(ip_address=ip))

        for (src_ip, src_port, dst_ip, dst_port, protocol), info in connections.items():
            result.connections.append(ParsedConnection(
                local_ip=src_ip,
                local_port=src_port,
                remote_ip=dst_ip,
                remote_port=dst_port,
                protocol=protocol,
                state=info["state"],
            ))

        if hosts or connections:
            result.success = True
            logger.info(f"Tcpdump parse complete: {len(hosts)} hosts, {len(connections)} connections")
        else:
            result.warnings.append("No valid tcpdump lines found")

        return result

    def parse_file(self, file_path: str) -> ParseResult:
        """
        Parse a PCAP file directly.

        Args:
            file_path: Path to the PCAP file

        Returns:
            ParseResult with extracted flows
        """
        return self.parse(file_path)


def get_flow_summary(result: ParseResult) -> Dict:
    """
    Generate a summary of flows from parse result.

    Returns statistics about:
    - Top talkers (by connection count)
    - Port distribution
    - Protocol breakdown
    """
    from collections import Counter

    summary = {
        "total_hosts": len(result.hosts),
        "total_connections": len(result.connections),
        "top_sources": [],
        "top_destinations": [],
        "top_ports": [],
        "protocol_breakdown": {"tcp": 0, "udp": 0, "icmp": 0, "other": 0},
    }

    src_counter = Counter()
    dst_counter = Counter()
    port_counter = Counter()

    for conn in result.connections:
        src_counter[conn.local_ip] += 1
        dst_counter[conn.remote_ip] += 1
        if conn.remote_port:
            port_counter[conn.remote_port] += 1

        protocol = conn.protocol.lower() if conn.protocol else "other"
        if protocol in summary["protocol_breakdown"]:
            summary["protocol_breakdown"][protocol] += 1
        else:
            summary["protocol_breakdown"]["other"] += 1

    summary["top_sources"] = [
        {"ip": ip, "count": count}
        for ip, count in src_counter.most_common(10)
    ]
    summary["top_destinations"] = [
        {"ip": ip, "count": count}
        for ip, count in dst_counter.most_common(10)
    ]
    summary["top_ports"] = [
        {"port": port, "count": count}
        for port, count in port_counter.most_common(10)
    ]

    return summary

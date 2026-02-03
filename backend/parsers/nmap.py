"""Parser for NMAP output in XML and greppable formats."""

import re
import logging
import xml.etree.ElementTree as ET
from typing import Optional, List
from .base import (
    BaseParser,
    ParseResult,
    ParsedHost,
    ParsedPort,
)

logger = logging.getLogger(__name__)


class NmapParser(BaseParser):
    """Parser for NMAP scan results in XML (-oX) and greppable (-oG) formats."""

    source_type: str = "nmap"

    def parse(self, data: str, format_hint: Optional[str] = None, **kwargs) -> ParseResult:
        """
        Parse NMAP output data.

        Args:
            data: The raw NMAP output data
            format_hint: Optional hint about format ("xml" or "grep")
            **kwargs: Additional arguments (unused for now)

        Returns:
            ParseResult containing parsed hosts and any errors/warnings
        """
        result = ParseResult(success=False, source_type=self.source_type)

        if not data or not data.strip():
            result.errors.append("Empty input data")
            return result

        # Auto-detect format if not provided
        detected_format = format_hint or self.detect_format(data)

        if detected_format == "xml":
            return self._parse_xml(data)
        elif detected_format == "grep":
            return self._parse_grep(data)
        else:
            result.errors.append(
                f"Unable to detect NMAP format. Detected: {detected_format}"
            )
            return result

    def detect_format(self, data: str) -> Optional[str]:
        """Detect whether input is XML or greppable NMAP format."""
        data_stripped = data.strip()

        # Check for XML format
        if data_stripped.startswith("<?xml") or data_stripped.startswith("<nmaprun"):
            return "xml"

        # Check for greppable format (lines starting with Host:)
        if "Host:" in data_stripped:
            return "grep"

        return None

    def _parse_xml(self, xml_data: str) -> ParseResult:
        """Parse NMAP XML output (-oX format)."""
        result = ParseResult(success=True, source_type=self.source_type)
        logger.info("Starting NMAP XML parsing")

        try:
            root = ET.fromstring(xml_data)
            logger.debug(f"XML root tag: {root.tag}")
        except ET.ParseError as e:
            result.success = False
            result.errors.append(f"XML parsing error: {str(e)}")
            logger.error(f"XML parsing error: {e}")
            return result

        # Find all host entries
        hosts = root.findall(".//host")
        logger.info(f"Found {len(hosts)} host(s) in NMAP output")

        if not hosts:
            result.warnings.append("No hosts found in NMAP output")
            return result

        for host_elem in hosts:
            try:
                parsed_host = self._parse_host_xml(host_elem)
                if parsed_host:
                    result.hosts.append(parsed_host)
                    logger.info(f"Parsed host: {parsed_host.ip_address} with {len(parsed_host.ports)} ports")
            except Exception as e:
                logger.exception(f"Error parsing host element: {e}")
                result.errors.append(f"Error parsing host element: {str(e)}")

        return result

    def _parse_host_xml(self, host_elem: ET.Element) -> Optional[ParsedHost]:
        """Parse a single host element from NMAP XML."""
        # Get IP address
        ip_address = None
        mac_address = None
        vendor = None

        for addr_elem in host_elem.findall(".//address"):
            addr_type = addr_elem.get("addrtype")
            addr = addr_elem.get("addr")

            if addr_type == "ipv4" or addr_type == "ipv6":
                ip_address = addr
            elif addr_type == "mac":
                mac_address = addr
                vendor = addr_elem.get("vendor")

        if not ip_address:
            return None

        # Get hostname(s)
        hostname = None
        fqdn = None
        for hostname_elem in host_elem.findall(".//hostname"):
            name = hostname_elem.get("name")
            h_type = hostname_elem.get("type")
            if h_type == "PTR":
                hostname = name
            elif h_type == "user":
                fqdn = name

        # Get OS information
        os_name = None
        os_family = None
        os_confidence = None

        os_elem = host_elem.find(".//osmatch")
        if os_elem is not None:
            os_name = os_elem.get("name")
            os_confidence = int(os_elem.get("accuracy", 0))
            if os_name:
                os_family = self._infer_os_family(os_name)

        # Parse ports
        ports = []
        for port_elem in host_elem.findall(".//port"):
            try:
                port = self._parse_port_xml(port_elem)
                if port:
                    ports.append(port)
            except Exception:
                # Skip malformed port entries
                continue

        # Create ParsedHost
        parsed_host = ParsedHost(
            ip_address=ip_address,
            mac_address=mac_address,
            hostname=hostname,
            fqdn=fqdn,
            vendor=vendor,
            os_name=os_name,
            os_family=os_family,
            os_confidence=os_confidence,
            ports=ports,
        )

        return parsed_host

    def _parse_port_xml(self, port_elem: ET.Element) -> Optional[ParsedPort]:
        """Parse a single port element from NMAP XML."""
        protocol = port_elem.get("protocol")  # tcp/udp
        port_id = port_elem.get("portid")

        if not protocol or not port_id:
            return None

        try:
            port_number = int(port_id)
        except ValueError:
            return None

        # Get port state
        state_elem = port_elem.find(".//state")
        state = state_elem.get("state") if state_elem is not None else "unknown"

        # Get service information
        service_elem = port_elem.find(".//service")
        service_name = None
        service_product = None
        service_version = None
        service_banner = None
        confidence = None

        if service_elem is not None:
            service_name = service_elem.get("name")
            service_product = service_elem.get("product")
            service_version = service_elem.get("version")
            service_banner = service_elem.get("extrainfo")
            confidence_str = service_elem.get("conf")
            if confidence_str:
                try:
                    confidence = int(confidence_str)
                except ValueError:
                    pass

        parsed_port = ParsedPort(
            port_number=port_number,
            protocol=protocol,
            state=state,
            service_name=service_name,
            service_product=service_product,
            service_version=service_version,
            service_banner=service_banner,
            confidence=confidence,
        )

        return parsed_port

    def _parse_grep(self, grep_data: str) -> ParseResult:
        """Parse NMAP greppable output (-oG format)."""
        result = ParseResult(success=True, source_type=self.source_type)
        lines = grep_data.strip().split("\n")

        for line in lines:
            # Skip comments and empty lines
            if not line.strip() or line.startswith("#"):
                continue

            # Parse Host: line
            if line.startswith("Host:"):
                try:
                    parsed_host = self._parse_host_grep(line)
                    if parsed_host:
                        result.hosts.append(parsed_host)
                except Exception as e:
                    result.errors.append(f"Error parsing grep line: {str(e)}")

        return result

    def _parse_host_grep(self, line: str) -> Optional[ParsedHost]:
        """Parse a single Host: line from NMAP greppable format.

        Example: Host: 192.168.1.1 ()	Ports: 22/open/tcp//ssh///,80/open/tcp//http///
        """
        # Extract IP address and hostname
        host_match = re.match(r"Host:\s+(\S+)\s+\(([^)]*)\)", line)
        if not host_match:
            return None

        ip_address = host_match.group(1)
        hostname_part = host_match.group(2).strip()

        hostname = hostname_part if hostname_part else None

        # Extract ports section
        ports = []
        ports_match = re.search(r"Ports:\s+(.+?)(?:\s+Ignored|\s*$)", line)
        if ports_match:
            ports_str = ports_match.group(1)
            ports = self._parse_ports_grep(ports_str)

        # Extract OS information if present
        os_name = None
        os_family = None
        os_confidence = None

        os_match = re.search(r"OS:\s+(.+?)(?:\s+MAC:|$)", line)
        if os_match:
            os_name = os_match.group(1).strip()
            os_family = self._infer_os_family(os_name)

        # Extract MAC address and vendor if present
        mac_address = None
        vendor = None
        mac_match = re.search(r"MAC:\s+([A-F0-9:]+)\s*\(([^)]+)\)?", line)
        if mac_match:
            mac_address = mac_match.group(1)
            vendor = mac_match.group(2).strip() if mac_match.group(2) else None

        parsed_host = ParsedHost(
            ip_address=ip_address,
            hostname=hostname,
            mac_address=mac_address,
            vendor=vendor,
            os_name=os_name,
            os_family=os_family,
            os_confidence=os_confidence,
            ports=ports,
        )

        return parsed_host

    def _parse_ports_grep(self, ports_str: str) -> List[ParsedPort]:
        """Parse ports string from greppable format.

        Format: port/state/protocol//service/version/hostname/extra_info/
        Example: 22/open/tcp//ssh/OpenSSH 8.9///,80/open/tcp//http///
        """
        ports = []
        port_entries = ports_str.split(",")

        for entry in port_entries:
            entry = entry.strip()
            if not entry:
                continue

            parts = entry.split("/")
            if len(parts) < 3:
                continue

            try:
                port_number = int(parts[0])
                state = parts[1]
                protocol = parts[2]

                # Extract service info if available
                # Greppable format: port/state/protocol/owner/service/version/extra/
                service_name = parts[4] if len(parts) > 4 and parts[4] else None
                service_info = parts[5] if len(parts) > 5 and parts[5] else None
                service_banner = parts[6] if len(parts) > 6 and parts[6] else None

                service_product = None
                service_version = None
                if service_info:
                    info_parts = service_info.split(" ", 1)
                    service_product = info_parts[0]
                    if len(info_parts) > 1 and info_parts[1]:
                        service_version = info_parts[1]

                parsed_port = ParsedPort(
                    port_number=port_number,
                    protocol=protocol,
                    state=state,
                    service_name=service_name,
                    service_product=service_product,
                    service_version=service_version,
                    service_banner=service_banner,
                )
                ports.append(parsed_port)
            except (ValueError, IndexError):
                # Skip malformed port entries
                continue

        return ports

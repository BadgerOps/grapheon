"""ARP output parser supporting Linux, macOS, and Windows formats."""

import re
from typing import Optional, List
from .base import BaseParser, ParseResult, ParsedArpEntry


class ArpParser(BaseParser):
    """Parser for ARP output in various formats."""

    source_type: str = "arp"

    def parse(self, data: str, platform: Optional[str] = None, **kwargs) -> ParseResult:
        """
        Parse ARP output and extract ARP entries.

        Args:
            data: Raw ARP output as string
            platform: Optional platform override ('linux', 'macos', 'windows')
            **kwargs: Additional arguments

        Returns:
            ParseResult containing parsed ARP entries
        """
        result = ParseResult(success=True, source_type=self.source_type)

        if not data or not data.strip():
            result.errors.append("Empty input data")
            result.success = False
            return result

        # Detect platform if not explicitly provided
        if not platform:
            platform = self.detect_format(data)

        if not platform:
            result.errors.append("Could not auto-detect ARP format")
            result.success = False
            return result

        try:
            arp_entries = self._parse_by_platform(data, platform)
            result.arp_entries = arp_entries
        except Exception as e:
            result.errors.append(f"Error parsing ARP data: {str(e)}")
            result.success = False

        return result

    def detect_format(self, data: str) -> Optional[str]:
        """
        Detect the ARP output format from input data.

        Returns:
            'linux', 'macos', 'windows', or None
        """
        lines = data.strip().split("\n")

        for line in lines:
            line = line.strip()

            # Windows format: "Interface: IP --- 0xN"
            if re.match(r"Interface:\s+[\d.]+\s+---\s+0x[0-9a-fA-F]", line):
                return "windows"

            # Windows header line: "  Internet Address      Physical Address"
            if re.match(r"\s*Internet Address\s+Physical Address\s+Type", line):
                return "windows"

            # Both Linux and macOS can start with "?" for unresolved hostnames.
            # Disambiguate using type markers: Linux uses [ether], macOS uses [ethernet] or ifscope.
            if re.match(r"\?\s+\([\d.]+\)\s+at\s+", line):
                if "[ether]" in line and "ifscope" not in line:
                    return "linux"
                if "ifscope" in line or "[ethernet]" in line:
                    return "macos"
                # Default to linux for ? lines without clear macOS markers
                return "linux"

            # Linux arp -a format: "router (192.168.1.1) at 00:11:22:33:44:55"
            # Note: Character class excludes ? to avoid matching macOS
            if re.match(r"[a-zA-Z0-9._-]+\s+\([\d.]+\)\s+at\s+", line):
                return "linux"

            # Linux ip neigh format: "192.168.1.1 dev eth0 lladdr 00:11:22:33:44:55"
            if re.match(r"[\d.]+\s+dev\s+\w+\s+lladdr\s+", line):
                return "linux"

            # Check for incomplete markers to identify format
            if "<incomplete>" in line:
                if "ether" in line:
                    return "linux"
                if "ifscope" in line:
                    return "macos"

            # Check for FAILED keyword (Linux ip neigh)
            if re.match(r"[\d.]+\s+dev\s+\w+\s+FAILED", line):
                return "linux"

        return None

    def _parse_by_platform(self, data: str, platform: str) -> List[ParsedArpEntry]:
        """Parse ARP output based on detected platform."""
        if platform == "linux":
            return self._parse_linux(data)
        elif platform == "macos":
            return self._parse_macos(data)
        elif platform == "windows":
            return self._parse_windows(data)
        else:
            return []

    def _parse_linux(self, data: str) -> List[ParsedArpEntry]:
        """
        Parse Linux ARP output (arp -a or ip neigh show).

        Handles both formats:
        - arp -a: router (192.168.1.1) at 00:11:22:33:44:55 [ether] on eth0
        - ip neigh: 192.168.1.1 dev eth0 lladdr 00:11:22:33:44:55 REACHABLE
        """
        entries = []
        lines = data.strip().split("\n")

        for line in lines:
            line = line.strip()

            # Skip empty lines and headers
            if not line or line.startswith("Address") or line.startswith("Neighbor"):
                continue

            # Try arp -a format first
            if " at " in line:
                entry = self._parse_linux_arp_format(line)
                if entry:
                    entries.append(entry)
            # Try ip neigh format
            elif " dev " in line:
                entry = self._parse_linux_ip_neigh_format(line)
                if entry:
                    entries.append(entry)

        return entries

    def _parse_linux_arp_format(self, line: str) -> Optional[ParsedArpEntry]:
        """Parse Linux arp -a format line."""
        # router (192.168.1.1) at 00:11:22:33:44:55 [ether] on eth0
        # ? (192.168.1.20) at <incomplete> on eth0
        match = re.match(
            r"[?a-zA-Z0-9._-]+\s+\(([\d.]+)\)\s+at\s+([0-9a-fA-F:]+|<incomplete>)\s+(?:\[[^\]]+\]\s+)?on\s+(\w+)",
            line,
        )

        if match:
            ip_address = match.group(1)
            mac_address = match.group(2)
            interface = match.group(3)

            # Handle incomplete entries
            if mac_address == "<incomplete>":
                mac_address = None
            else:
                mac_address = self._normalize_mac(mac_address)

            return ParsedArpEntry(
                ip_address=ip_address,
                mac_address=mac_address,
                interface=interface,
                entry_type="dynamic",
                vendor=None,
            )

        return None

    def _parse_linux_ip_neigh_format(self, line: str) -> Optional[ParsedArpEntry]:
        """Parse Linux ip neigh show format line."""
        # 192.168.1.1 dev eth0 lladdr 00:11:22:33:44:55 REACHABLE
        # 192.168.1.20 dev eth0  FAILED
        match = re.match(r"([\d.]+)\s+dev\s+(\w+)\s+(?:lladdr\s+([0-9a-fA-F:]+))?\s*(.*)", line)

        if match:
            ip_address = match.group(1)
            interface = match.group(2)
            mac_address = match.group(3)
            state = match.group(4).strip() if match.group(4) else ""

            # Handle missing MAC address (FAILED entries)
            if not mac_address:
                mac_address = None
            else:
                mac_address = self._normalize_mac(mac_address)

            # Determine entry type from state
            entry_type = "dynamic"  # Default
            if "FAILED" in state:
                entry_type = "failed"
            elif "PERMANENT" in state:
                entry_type = "permanent"

            return ParsedArpEntry(
                ip_address=ip_address,
                mac_address=mac_address,
                interface=interface,
                entry_type=entry_type,
                vendor=None,
            )

        return None

    def _parse_macos(self, data: str) -> List[ParsedArpEntry]:
        """
        Parse macOS ARP output (arp -a).

        Format: ? (192.168.1.1) at 0:11:22:33:44:55 on en0 ifscope [ethernet]
        """
        entries = []
        lines = data.strip().split("\n")

        for line in lines:
            line = line.strip()

            # Skip empty lines and headers
            if not line or not line.startswith("?"):
                continue

            # Parse macOS format
            # ? (192.168.1.1) at 0:11:22:33:44:55 on en0 ifscope [ethernet]
            # ? (192.168.1.20) at (incomplete) on en0 ifscope [ethernet]
            match = re.match(
                r"\?\s+\(([\d.]+)\)\s+at\s+(.+?)\s+on\s+(\w+)",
                line,
            )

            if match:
                ip_address = match.group(1)
                mac_address = match.group(2).strip()
                interface = match.group(3)

                # Handle incomplete entries
                if mac_address in ("<incomplete>", "(incomplete)"):
                    mac_address = None
                else:
                    mac_address = self._normalize_mac(mac_address)

                entry = ParsedArpEntry(
                    ip_address=ip_address,
                    mac_address=mac_address,
                    interface=interface,
                    entry_type="dynamic",
                    vendor=None,
                )
                entries.append(entry)

        return entries

    def _parse_windows(self, data: str) -> List[ParsedArpEntry]:
        """
        Parse Windows ARP output (arp -a).

        Format:
        Interface: 192.168.1.100 --- 0x4
          Internet Address      Physical Address      Type
          192.168.1.1           00-11-22-33-44-55     dynamic
        """
        entries = []
        lines = data.strip().split("\n")
        current_interface = None

        for line in lines:
            # Detect interface line
            interface_match = re.match(r"Interface:\s+([\d.]+)\s+---", line)
            if interface_match:
                current_interface = interface_match.group(1)
                continue

            # Skip empty lines and header lines
            if not line.strip() or "Internet Address" in line or "Physical Address" in line:
                continue

            # Parse ARP entry line
            # Format: "192.168.1.1           00-11-22-33-44-55     dynamic"
            parts = line.split()
            if len(parts) >= 3:
                # Check if first part looks like IP address
                ip_match = re.match(r"[\d.]+", parts[0])
                if ip_match:
                    ip_address = parts[0]
                    # MAC address is separated by whitespace, may have dashes
                    mac_address = parts[1]
                    # Type is at the end
                    entry_type = parts[2].lower() if len(parts) > 2 else "dynamic"

                    # Normalize MAC address (Windows uses dashes, we want colons)
                    mac_address = self._normalize_mac(mac_address)

                    entry = ParsedArpEntry(
                        ip_address=ip_address,
                        mac_address=mac_address,
                        interface=current_interface,
                        entry_type=entry_type,
                        vendor=None,
                    )
                    entries.append(entry)

        return entries

    def _normalize_mac(self, mac: str) -> str:
        """
        Normalize MAC address to lowercase with colons.

        Handles:
        - 00:11:22:33:44:55 -> 00:11:22:33:44:55
        - 00-11-22-33-44-55 -> 00:11:22:33:44:55
        - 0:11:22:33:44:55 -> 00:11:22:33:44:55
        """
        if not mac:
            return mac

        # Remove any whitespace
        mac = mac.strip()

        # Strip trailing type markers like [ether], [ethernet]
        mac = re.sub(r'\s*\[.*\]', '', mac)

        # Replace dashes with colons
        mac = mac.replace("-", ":")

        # Split and rejoin to handle inconsistent formats
        parts = mac.split(":")
        if len(parts) == 6:
            # Pad single-digit hex values with leading zero
            normalized_parts = [part.zfill(2) for part in parts]
            return ":".join(normalized_parts).lower()

        # If not 6 parts, return as-is (lowercase)
        return mac.lower()

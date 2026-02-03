"""Parser for traceroute output in multiple formats."""

import re
from typing import Optional
from .base import (
    BaseParser,
    ParseResult,
    ParsedRouteHop,
)


class TracerouteParser(BaseParser):
    """Parser for traceroute results in Linux/macOS, Windows, and MTR formats."""

    source_type: str = "traceroute"

    def parse(self, data: str, format_hint: Optional[str] = None, **kwargs) -> ParseResult:
        """
        Parse traceroute output data.

        Args:
            data: The raw traceroute output data
            format_hint: Optional hint about format ("linux", "windows", "mtr")
            **kwargs: Additional arguments (unused for now)

        Returns:
            ParseResult containing parsed route hops and any errors/warnings
        """
        result = ParseResult(success=False, source_type=self.source_type)

        if not data or not data.strip():
            result.errors.append("Empty input data")
            return result

        # Auto-detect format if not provided
        detected_format = format_hint or self.detect_format(data)

        if detected_format == "linux":
            return self._parse_linux(data)
        elif detected_format == "windows":
            return self._parse_windows(data)
        elif detected_format == "mtr":
            return self._parse_mtr(data)
        else:
            result.errors.append(
                f"Unable to detect traceroute format. Detected: {detected_format}"
            )
            return result

    def detect_format(self, data: str) -> Optional[str]:
        """Detect whether input is Linux/macOS, Windows, or MTR format."""
        data_stripped = data.strip()

        # Check for Windows format (starts with "Tracing route")
        if "Tracing route" in data_stripped:
            return "windows"

        # Check for MTR format (contains pipe symbols and loss% column)
        if "Loss%" in data_stripped and "|--" in data_stripped:
            return "mtr"

        # Check for Linux/macOS format (contains "traceroute to" or hops with ms)
        if "traceroute to" in data_stripped or "traceroute " in data_stripped:
            return "linux"

        # Try to detect by lines starting with numbers (hops)
        lines = data_stripped.split("\n")
        for line in lines:
            # Linux/macOS hop line: " 1  router.local (192.168.1.1)  1.234 ms"
            if re.match(r"\s*\d+\s+", line) and "ms" in line.lower():
                return "linux"
            # Windows hop line: "  1     1 ms     1 ms     1 ms  router.local"
            if re.match(r"\s*\d+\s+\d+\s+ms", line):
                return "windows"

        return None

    def _parse_linux(self, data: str) -> ParseResult:
        """Parse Linux/macOS traceroute output."""
        result = ParseResult(success=True, source_type=self.source_type)
        lines = data.strip().split("\n")

        # Extract destination from header (currently unused)
        for line in lines[:3]:  # Check first few lines for header
            # Match "traceroute to google.com (142.250.80.46)"
            dest_match = re.search(r"traceroute to\s+\S+\s+\(([^)]+)\)", line)
            if dest_match:
                break

        # Parse hop lines
        for line in lines:
            line = line.strip()
            if not line or "traceroute to" in line or "max" in line.lower():
                continue

            # Match hop line: " 1  router.local (192.168.1.1)  1.234 ms  1.123 ms  1.456 ms"
            # Or just IP: " 2  10.0.0.1 (10.0.0.1)  5.678 ms  5.432 ms  5.789 ms"
            # Or timeout: " 3  * * *"
            hop_match = re.match(r"\s*(\d+)\s+(.+)", line)
            if not hop_match:
                continue

            hop_number_str = hop_match.group(1)
            hop_content = hop_match.group(2)

            try:
                hop_number = int(hop_number_str)
            except ValueError:
                continue

            # Check for timeout (all asterisks)
            if re.match(r"^\*\s+\*\s+\*", hop_content.strip()):
                route_hop = ParsedRouteHop(hop_number=hop_number)
                result.route_hops.append(route_hop)
                continue

            # Parse hostname and IP
            hostname = None
            ip_address = None

            # Try to match "hostname (ip)" pattern
            host_ip_match = re.match(r"(\S+)\s+\(([^)]+)\)\s+(.+)", hop_content)
            if host_ip_match:
                hostname = host_ip_match.group(1)
                ip_address = host_ip_match.group(2)
                rtt_str = host_ip_match.group(3)
            else:
                # Try to match just "ip rtt..." pattern
                parts = hop_content.split()
                if parts:
                    ip_address = parts[0]
                    rtt_str = " ".join(parts[1:])
                else:
                    continue

            # Parse RTT values (up to 3 samples)
            rtt_values = []
            rtt_matches = re.findall(r"(\d+\.?\d*)\s*ms", rtt_str)
            for rtt_match in rtt_matches[:3]:  # Take up to 3 samples
                try:
                    rtt_values.append(float(rtt_match))
                except ValueError:
                    pass

            route_hop = ParsedRouteHop(
                hop_number=hop_number, ip_address=ip_address, hostname=hostname, rtt_ms=rtt_values
            )
            result.route_hops.append(route_hop)

        if not result.route_hops:
            result.errors.append("No hop data found in traceroute output")
            result.success = False

        return result

    def _parse_windows(self, data: str) -> ParseResult:
        """Parse Windows tracert output."""
        result = ParseResult(success=True, source_type=self.source_type)
        lines = data.strip().split("\n")

        # Extract destination from header (currently unused)
        for line in lines[:3]:  # Check first few lines for header
            # Match "Tracing route to google.com [142.250.80.46]"
            dest_match = re.search(r"Tracing route to\s+\S+\s+\[([^\]]+)\]", line)
            if dest_match:
                break

        # Parse hop lines
        for line in lines:
            line_stripped = line.strip()

            # Skip header, footer, and empty lines
            if (
                not line_stripped
                or "Tracing route" in line
                or "maximum" in line.lower()
                or "Trace complete" in line
                or line_stripped.startswith("over a maximum")
            ):
                continue

            # Windows format: "  1     1 ms     1 ms     1 ms  router.local [192.168.1.1]"
            # Or with Request timed out: "  3     *        *        *     Request timed out."
            # Match hop number at start
            hop_match = re.match(r"\s*(\d+)\s+(.+)", line)
            if not hop_match:
                continue

            hop_number_str = hop_match.group(1)
            hop_content = hop_match.group(2)

            try:
                hop_number = int(hop_number_str)
            except ValueError:
                continue

            # Check for "Request timed out"
            if "Request timed out" in hop_content:
                route_hop = ParsedRouteHop(hop_number=hop_number)
                result.route_hops.append(route_hop)
                continue

            # Parse RTT values and hostname/IP
            # Format: "1 ms     1 ms     1 ms  router.local [192.168.1.1]"
            # Or: "1 ms     1 ms     1 ms  142.250.80.46"

            # Extract RTT values (they come before the hostname)
            rtt_values = []
            rtt_matches = re.findall(r"(\d+)\s*ms", hop_content)
            for rtt_match in rtt_matches[:3]:  # Take up to 3 samples
                try:
                    rtt_values.append(float(rtt_match))
                except ValueError:
                    pass

            # Extract hostname and IP
            # Look for "hostname [ip]" pattern
            hostname = None
            ip_address = None

            host_ip_match = re.search(r"(\S+)\s+\[([^\]]+)\]", hop_content)
            if host_ip_match:
                hostname = host_ip_match.group(1)
                ip_address = host_ip_match.group(2)
            else:
                # Just an IP without brackets
                # Remove RTT values from the line and get the last token
                remaining = re.sub(r"\d+\s*ms", "", hop_content).strip()
                if remaining:
                    ip_address = remaining.split()[-1]

            route_hop = ParsedRouteHop(
                hop_number=hop_number, ip_address=ip_address, hostname=hostname, rtt_ms=rtt_values
            )
            result.route_hops.append(route_hop)

        if not result.route_hops:
            result.errors.append("No hop data found in tracert output")
            result.success = False

        return result

    def _parse_mtr(self, data: str) -> ParseResult:
        """Parse MTR (My Traceroute) output."""
        result = ParseResult(success=True, source_type=self.source_type)
        lines = data.strip().split("\n")

        for line in lines:
            line_stripped = line.strip()

            # Skip header line and empty lines
            if not line_stripped or "HOST:" in line or "Loss%" in line:
                continue

            # MTR format: "  1.|-- router.local              0.0%    10    1.2   1.3   1.1   1.5   0.1"
            # Match hop line starting with number and pipe
            hop_match = re.match(r"\s*(\d+)\.\|--\s+(\S+)\s+", line_stripped)
            if not hop_match:
                continue

            hop_number_str = hop_match.group(1)
            hostname_or_ip = hop_match.group(2)

            try:
                hop_number = int(hop_number_str)
            except ValueError:
                continue

            # Determine if it's hostname or IP
            ip_address = None
            hostname = None

            if self._is_ip_address(hostname_or_ip):
                ip_address = hostname_or_ip
            else:
                hostname = hostname_or_ip

            # Extract the "Last" latency value from MTR columns
            # Format: "Host ... Loss% Snt Last Avg Best Wrst StDev"
            # The "Last" column is after loss%, packets sent, and before Avg
            rtt_values = []

            # Extract all numeric values after hostname
            remaining = line_stripped[hop_match.end() :]
            values = re.findall(r"([\d.]+)(?:%|\s)", remaining)

            # Skip first value (loss percentage) and get the numeric RTT values
            # Usually: Loss%, Snt, Last, Avg, Best, Wrst, StDev
            if len(values) >= 3:
                # Try to get Last (index 2), Avg (index 3), Best (index 4)
                try:
                    last_rtt = float(values[2])
                    avg_rtt = float(values[3]) if len(values) > 3 else None
                    best_rtt = float(values[4]) if len(values) > 4 else None

                    # Store Last, Avg, Best as RTT samples
                    if last_rtt > 0:
                        rtt_values.append(last_rtt)
                    if avg_rtt and avg_rtt > 0:
                        rtt_values.append(avg_rtt)
                    if best_rtt and best_rtt > 0:
                        rtt_values.append(best_rtt)
                except (ValueError, IndexError):
                    pass

            route_hop = ParsedRouteHop(
                hop_number=hop_number, ip_address=ip_address, hostname=hostname, rtt_ms=rtt_values
            )
            result.route_hops.append(route_hop)

        if not result.route_hops:
            result.errors.append("No hop data found in MTR output")
            result.success = False

        return result

    @staticmethod
    def _is_ip_address(value: str) -> bool:
        """Check if a string is an IP address."""
        # Simple check for IPv4
        parts = value.split(".")
        if len(parts) == 4:
            try:
                for part in parts:
                    num = int(part)
                    if num < 0 or num > 255:
                        return False
                return True
            except ValueError:
                pass

        # Simple check for IPv6 (contains colons)
        if ":" in value:
            return True

        return False

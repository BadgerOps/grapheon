"""Parser for ping output in multiple formats."""

import re
from typing import Optional
from .base import (
    BaseParser,
    ParseResult,
    ParsedHost,
)


class PingParser(BaseParser):
    """Parser for ping results in IP list, fping, nmap -sn, and standard ping formats."""

    source_type: str = "ping"

    def parse(self, data: str, format_hint: Optional[str] = None, **kwargs) -> ParseResult:
        """
        Parse ping output data.

        Args:
            data: The raw ping output data
            format_hint: Optional hint about format ("iplist", "fping", "nmap", "standard")
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

        if detected_format == "iplist":
            return self._parse_iplist(data)
        elif detected_format == "fping":
            return self._parse_fping(data)
        elif detected_format == "nmap":
            return self._parse_nmap_ping(data)
        elif detected_format == "standard":
            return self._parse_standard_ping(data)
        else:
            result.errors.append(f"Unable to detect ping format. Detected: {detected_format}")
            return result

    def detect_format(self, data: str) -> Optional[str]:
        """Detect whether input is IP list, fping, nmap -sn, or standard ping format."""
        data_stripped = data.strip()
        lines = data_stripped.split("\n")

        # Check for nmap -sn format
        if "Nmap scan report" in data_stripped or "Nmap done:" in data_stripped:
            return "nmap"

        # Check for fping format (lines with "is alive" or "is unreachable")
        if re.search(r"is (alive|unreachable)", data_stripped):
            return "fping"

        # Check for standard ping output
        if re.search(r"PING\s+\S+.*bytes", data_stripped) or re.search(
            r"ping statistics", data_stripped.lower()
        ):
            return "standard"

        # Check if it's a simple IP list (most lines are valid IPs)
        ip_count = 0
        valid_lines = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            valid_lines += 1
            if self._is_valid_ip(line):
                ip_count += 1

        # If more than 50% of non-empty lines are IPs, treat as IP list
        if valid_lines > 0 and ip_count / valid_lines > 0.5:
            return "iplist"

        return None

    def _parse_iplist(self, data: str) -> ParseResult:
        """Parse simple IP list format (one IP per line)."""
        result = ParseResult(success=True, source_type=self.source_type)
        lines = data.strip().split("\n")

        ip_count = 0
        for line in lines:
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Validate and add as alive host
            if self._is_valid_ip(line):
                parsed_host = ParsedHost(ip_address=line)
                result.hosts.append(parsed_host)
                ip_count += 1

        if ip_count == 0:
            result.errors.append("No valid IPs found in IP list")
            result.success = False
        else:
            result.success = True

        return result

    def _parse_fping(self, data: str) -> ParseResult:
        """Parse fping output format."""
        result = ParseResult(success=True, source_type=self.source_type)
        lines = data.strip().split("\n")

        for line in lines:
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # fping format: "192.168.1.1 is alive"
            # Or with latency: "192.168.1.10 is alive (25.3 ms)"
            # Or unreachable: "192.168.1.2 is unreachable"

            # Match "IP is alive/unreachable" pattern
            alive_match = re.match(r"(\S+)\s+is\s+alive(?:\s+\(([^)]+)\))?", line)
            if alive_match:
                ip_address = alive_match.group(1)

                # Skip non-IP entries
                if not self._is_valid_ip(ip_address):
                    continue

                parsed_host = ParsedHost(ip_address=ip_address)

                # Extract latency if present
                latency_str = alive_match.group(2)
                if latency_str:
                    # Extract numeric value from "25.3 ms"
                    latency_match = re.search(r"([\d.]+)", latency_str)
                    if latency_match:
                        try:
                            # Store latency in metadata if needed (currently no field for it)
                            pass
                        except ValueError:
                            pass

                result.hosts.append(parsed_host)
                continue

            # Check for unreachable
            unreachable_match = re.match(r"(\S+)\s+is\s+unreachable", line)
            if unreachable_match:
                # Skip unreachable hosts (we only return alive hosts)
                continue

        if not result.hosts:
            result.warnings.append("No alive hosts found in fping output")

        return result

    def _parse_nmap_ping(self, data: str) -> ParseResult:
        """Parse nmap -sn ping scan output."""
        result = ParseResult(success=True, source_type=self.source_type)
        lines = data.strip().split("\n")

        current_ip = None
        current_hostname = None
        current_mac = None
        current_vendor = None

        for line in lines:
            line_stripped = line.strip()

            # Skip lines that don't contain scan report
            if "Nmap scan report" not in line_stripped and "Host is up" not in line_stripped and "MAC Address" not in line_stripped:
                continue

            # Parse "Nmap scan report for hostname/IP (IP)"
            if "Nmap scan report" in line_stripped:
                # Save previous host if exists
                if current_ip:
                    parsed_host = ParsedHost(
                        ip_address=current_ip,
                        hostname=current_hostname,
                        mac_address=current_mac,
                        vendor=current_vendor,
                    )
                    result.hosts.append(parsed_host)

                # Reset for new host
                current_ip = None
                current_hostname = None
                current_mac = None
                current_vendor = None

                # Extract hostname and IP
                # Format: "Nmap scan report for router.local (192.168.1.1)"
                # Or: "Nmap scan report for 192.168.1.5"
                report_match = re.search(r"Nmap scan report for\s+(\S+)(?:\s+\(([^)]+)\))?", line_stripped)
                if report_match:
                    first_part = report_match.group(1)
                    ip_part = report_match.group(2)

                    if ip_part:
                        # Has both hostname and IP
                        if self._is_valid_ip(first_part):
                            current_ip = first_part
                        else:
                            current_hostname = first_part
                            current_ip = ip_part
                    else:
                        # Just hostname or IP
                        if self._is_valid_ip(first_part):
                            current_ip = first_part
                        else:
                            current_hostname = first_part

            # Parse "Host is up (latency)"
            elif "Host is up" in line_stripped and current_ip:
                # Latency data is currently not stored.
                pass

            # Parse "MAC Address: 00:11:22:33:44:55 (Vendor)"
            elif "MAC Address:" in line_stripped and current_ip:
                # Format: "MAC Address: 00:11:22:33:44:55 (Cisco Systems)"
                mac_match = re.search(
                    r"MAC Address:\s+([A-F0-9:]+)\s+(?:\(([^)]+)\))?", line_stripped, re.IGNORECASE
                )
                if mac_match:
                    current_mac = mac_match.group(1)
                    current_vendor = mac_match.group(2).strip() if mac_match.group(2) else None

        # Add last host
        if current_ip:
            parsed_host = ParsedHost(
                ip_address=current_ip,
                hostname=current_hostname,
                mac_address=current_mac,
                vendor=current_vendor,
            )
            result.hosts.append(parsed_host)

        if not result.hosts:
            result.warnings.append("No alive hosts found in nmap -sn output")

        return result

    def _parse_standard_ping(self, data: str) -> ParseResult:
        """Parse standard ping output (single host)."""
        result = ParseResult(success=True, source_type=self.source_type)
        lines = data.strip().split("\n")

        target_ip = None
        target_hostname = None
        latency_sum = 0
        latency_count = 0
        packets_transmitted = None
        packets_received = None

        for line in lines:
            line_stripped = line.strip()

            # Parse PING header line to extract target
            if line_stripped.startswith("PING"):
                # Format: "PING 192.168.1.1 (192.168.1.1) 56(84) bytes of data."
                # Or: "PING router.local (192.168.1.1) ..."
                ping_match = re.search(r"PING\s+(\S+)(?:\s+\(([^)]+)\))?", line_stripped)
                if ping_match:
                    first_part = ping_match.group(1)
                    ip_part = ping_match.group(2)

                    if ip_part:
                        if self._is_valid_ip(first_part):
                            target_ip = first_part
                        else:
                            target_hostname = first_part
                            target_ip = ip_part
                    else:
                        if self._is_valid_ip(first_part):
                            target_ip = first_part
                        else:
                            target_hostname = first_part

            # Parse individual ping responses
            # Format: "64 bytes from 192.168.1.1: icmp_seq=1 ttl=64 time=1.23 ms"
            elif "bytes from" in line_stripped and "time=" in line_stripped:
                time_match = re.search(r"time=([0-9.]+)\s*ms", line_stripped)
                if time_match:
                    try:
                        latency = float(time_match.group(1))
                        latency_sum += latency
                        latency_count += 1
                    except ValueError:
                        pass

            # Parse statistics line
            # Format: "3 packets transmitted, 3 received, 0% packet loss, time 2003ms"
            elif "packets transmitted" in line_stripped.lower():
                transmitted_match = re.search(r"(\d+)\s+packets transmitted", line_stripped)
                if transmitted_match:
                    packets_transmitted = int(transmitted_match.group(1))

                received_match = re.search(r"(\d+)\s+received", line_stripped)
                if received_match:
                    packets_received = int(received_match.group(1))


        # Only add host if we have an IP and received packets
        if target_ip and packets_received and packets_received > 0:
            parsed_host = ParsedHost(ip_address=target_ip, hostname=target_hostname)
            result.hosts.append(parsed_host)
        elif target_ip:
            # Add host even if no packets received, but mark as potentially down
            parsed_host = ParsedHost(ip_address=target_ip, hostname=target_hostname)
            result.hosts.append(parsed_host)
            if packets_transmitted == 0 or packets_received == 0:
                result.warnings.append(f"No response from {target_ip}")

        if not result.hosts:
            result.errors.append("No host found in ping output")
            result.success = False

        return result

    @staticmethod
    def _is_valid_ip(value: str) -> bool:
        """Check if a string is a valid IP address."""
        # Simple IPv4 check
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

        # Simple IPv6 check (contains colons)
        if ":" in value and value.count(":") >= 2:
            return True

        return False

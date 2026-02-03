"""Netstat output parser supporting Linux, macOS, and Windows formats."""

import re
from typing import Optional, List, Tuple
from .base import BaseParser, ParseResult, ParsedConnection


class NetstatParser(BaseParser):
    """Parser for netstat output in various formats."""

    source_type: str = "netstat"

    def parse(self, data: str, platform: Optional[str] = None, **kwargs) -> ParseResult:
        """
        Parse netstat output and extract connection information.

        Args:
            data: Raw netstat output as string
            platform: Optional platform override ('linux', 'macos', 'windows')
            **kwargs: Additional arguments

        Returns:
            ParseResult containing parsed connections
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
            result.errors.append("Could not auto-detect netstat format")
            result.success = False
            return result

        try:
            connections = self._parse_by_platform(data, platform)
            result.connections = connections
        except Exception as e:
            result.errors.append(f"Error parsing netstat data: {str(e)}")
            result.success = False

        return result

    def detect_format(self, data: str) -> Optional[str]:
        """
        Detect the netstat format from input data.

        Returns:
            'linux', 'macos', 'windows', or None
        """
        lines = data.strip().split("\n")

        for line in lines:
            # Linux format has PID/Program name column (e.g., "1234/sshd" or just numbers)
            if re.search(r"Proto\s+Recv-Q\s+Send-Q\s+Local\s+Address\s+Foreign\s+Address\s+State", line):
                return "linux"

            # Windows format has specific header pattern
            if re.search(r"Proto\s+Local\s+Address\s+Foreign\s+Address\s+State\s+PID", line):
                return "windows"

            # macOS format header
            if re.search(
                r"Proto\s+Recv-Q\s+Send-Q\s+Local\s+Address\s+Foreign\s+Address", line
            ):
                if "(state)" in line.lower():
                    return "macos"
                if "state" in line.lower():
                    # Could be either Linux or macOS, check for more context
                    continue

            # Check for actual connection lines to distinguish formats
            # Linux/macOS have IPv4/IPv6 indicators in proto (tcp4, tcp6, udp4, etc. for macOS/Windows)
            if re.match(r"^\s*(tcp|udp|TCP|UDP)", line):
                # Windows uses TCP/UDP in uppercase
                if re.match(r"^\s*(TCP|UDP)", line):
                    # Check if it has the Windows-style bracketed IPv6
                    if "[" in line:
                        return "windows"
                # Linux/macOS use lowercase or with version numbers
                if "tcp" in line.lower():
                    # Distinguish Linux from macOS by checking for PID column
                    if re.search(r"/[a-zA-Z0-9_-]+\s*$", line):
                        return "linux"
                    # macOS doesn't have PID in netstat -an output
                    return "macos"

        return None

    def _parse_by_platform(self, data: str, platform: str) -> List[ParsedConnection]:
        """Parse netstat output based on detected platform."""
        if platform == "linux":
            return self._parse_linux(data)
        elif platform == "macos":
            return self._parse_macos(data)
        elif platform == "windows":
            return self._parse_windows(data)
        else:
            return []

    def _parse_linux(self, data: str) -> List[ParsedConnection]:
        """Parse Linux netstat output (netstat -tulpn)."""
        connections = []
        lines = data.strip().split("\n")
        in_header = False

        for line in lines:
            # Skip empty lines
            if not line.strip():
                continue

            # Find header line
            if "Proto" in line and "Recv-Q" in line:
                in_header = True
                continue

            if not in_header:
                continue

            # Parse connection line
            parts = line.split()
            if len(parts) < 5:
                continue

            proto = parts[0]
            local_addr = parts[3]
            foreign_addr = parts[4]

            state = "UNKNOWN"
            pid_name = None

            if proto.lower().startswith("udp"):
                # UDP lines often omit the State column in netstat -tulpn output.
                if len(parts) > 6:
                    state = parts[5]
                    pid_name = parts[6]
                elif len(parts) > 5:
                    pid_name = parts[5]
            else:
                if len(parts) > 5:
                    state = parts[5]
                if len(parts) > 6:
                    pid_name = parts[6]

            # Parse addresses
            local_ip, local_port = self._parse_address(local_addr)
            remote_ip, remote_port = self._parse_address(foreign_addr)

            if local_ip is None or remote_ip is None:
                continue

            # Extract PID and process name
            pid = None
            process_name = None
            if pid_name:
                pid, process_name = self._parse_pid_name(pid_name)

            # Normalize state
            normalized_state = self._normalize_state(state)

            # Extract protocol type (tcp/udp from tcp/tcp6/udp/udp6)
            proto_type = "tcp" if "tcp" in proto.lower() else "udp"

            connection = ParsedConnection(
                local_ip=local_ip,
                local_port=local_port,
                remote_ip=remote_ip,
                remote_port=remote_port,
                protocol=proto_type,
                state=normalized_state,
                pid=pid,
                process_name=process_name,
            )
            connections.append(connection)

        return connections

    def _parse_macos(self, data: str) -> List[ParsedConnection]:
        """Parse macOS netstat output (netstat -an)."""
        connections = []
        lines = data.strip().split("\n")
        in_header = False

        for line in lines:
            # Skip empty lines
            if not line.strip():
                continue

            # Skip header lines
            if "Proto" in line or "Active Internet" in line:
                in_header = True
                continue

            if not in_header:
                continue

            # Parse connection line - macOS format has Recv-Q and Send-Q columns
            # tcp4       0      0  *.22                   *.*                    LISTEN
            # udp4       0      0  *.68                   *.*
            parts = line.split()
            if len(parts) < 5:  # Need at least: proto, recv-q, send-q, local, foreign
                continue

            proto = parts[0]
            # Skip Recv-Q (parts[1]) and Send-Q (parts[2])
            local_addr = parts[3]
            foreign_addr = parts[4]
            state = parts[5] if len(parts) > 5 else "UNKNOWN"

            # Parse addresses (macOS uses dots for colons in ports)
            local_ip, local_port = self._parse_macos_address(local_addr)
            remote_ip, remote_port = self._parse_macos_address(foreign_addr)

            if local_ip is None or remote_ip is None:
                continue

            # Normalize state
            normalized_state = self._normalize_state(state)

            # Extract protocol type (tcp4/tcp6/udp4/udp6)
            proto_type = "tcp" if "tcp" in proto.lower() else "udp"

            connection = ParsedConnection(
                local_ip=local_ip,
                local_port=local_port,
                remote_ip=remote_ip,
                remote_port=remote_port,
                protocol=proto_type,
                state=normalized_state,
                pid=None,
                process_name=None,
            )
            connections.append(connection)

        return connections

    def _parse_windows(self, data: str) -> List[ParsedConnection]:
        """Parse Windows netstat output (netstat -ano)."""
        connections = []
        lines = data.strip().split("\n")
        in_header = False

        for line in lines:
            # Skip empty lines
            if not line.strip():
                continue

            # Skip "Active Connections" header
            if "Active Connections" in line or line.strip().startswith("Proto"):
                in_header = True
                continue

            if not in_header:
                continue

            # Parse connection line
            parts = line.split()
            if len(parts) < 4:
                continue

            proto = parts[0]
            local_addr = parts[1]
            foreign_addr = parts[2]
            state = None
            pid = None
            if proto.upper() == "UDP":
                # Windows UDP output omits the State column: UDP <local> <foreign> <pid>
                if len(parts) > 3 and parts[3].isdigit():
                    pid = int(parts[3])
                elif len(parts) > 4 and parts[4].isdigit():
                    state = parts[3]
                    pid = int(parts[4])
                state = state or "UNKNOWN"
            else:
                state = parts[3]
                pid = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else None

            # Parse addresses
            local_ip, local_port = self._parse_address(local_addr)
            remote_ip, remote_port = self._parse_address(foreign_addr)

            if local_ip is None or remote_ip is None:
                continue

            # Normalize state
            normalized_state = self._normalize_state(state or "UNKNOWN")

            # Extract protocol type
            proto_type = "tcp" if "TCP" in proto else "udp"

            connection = ParsedConnection(
                local_ip=local_ip,
                local_port=local_port,
                remote_ip=remote_ip,
                remote_port=remote_port,
                protocol=proto_type,
                state=normalized_state,
                pid=pid,
                process_name=None,
            )
            connections.append(connection)

        return connections

    def _parse_address(self, addr: str) -> Tuple[Optional[str], Optional[int]]:
        """
        Parse address in Linux/Windows format (IP:port).

        Handles:
        - 0.0.0.0:22 -> ('0.0.0.0', 22)
        - [::]:80 -> ('::', 80)
        - 192.168.1.10:443 -> ('192.168.1.10', 443)
        """
        # Handle IPv6 addresses in brackets
        if addr.startswith("["):
            # Format: [::]:80 or [::1]:8080
            match = re.match(r"\[([^\]]+)\]:(\d+)", addr)
            if match:
                return (match.group(1), int(match.group(2)))
            return (None, None)

        # Handle wildcard
        if addr in ("0.0.0.0:*", "*:*"):
            return ("0.0.0.0", None)

        # Handle IPv4 addresses
        if ":" in addr:
            parts = addr.rsplit(":", 1)
            if len(parts) == 2 and parts[1].isdigit():
                return (parts[0], int(parts[1]))
            elif len(parts) == 2 and parts[1] == "*":
                return (parts[0], None)

        return (None, None)

    def _parse_macos_address(self, addr: str) -> Tuple[Optional[str], Optional[int]]:
        """
        Parse address in macOS format where colons in ports are replaced with dots.

        Handles:
        - *.22 -> ('*', 22)
        - 192.168.1.10.443 -> ('192.168.1.10', 443)
        - *.* -> ('*', None)
        """
        # Handle wildcard addresses
        if addr == "*" or addr == "*.*":
            return ("0.0.0.0", None)

        if addr.startswith("*."):
            port_str = addr[2:]
            if port_str.isdigit():
                return ("0.0.0.0", int(port_str))
            return ("0.0.0.0", None)

        # For IPv6 (starts with ::)
        if addr.startswith("::"):
            # Format like ::1.8080 or just ::
            if "." in addr:
                parts = addr.rsplit(".", 1)
                if parts[1].isdigit():
                    return (parts[0], int(parts[1]))
            return (addr, None)

        # For regular IPv4 addresses, the last dot-separated component is the port
        # 192.168.1.10.443 -> ('192.168.1.10', 443)
        parts = addr.rsplit(".", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return (parts[0], int(parts[1]))

        return (None, None)

    def _parse_pid_name(self, pid_name: str) -> Tuple[Optional[int], Optional[str]]:
        """
        Parse PID/program name from format like "1234/sshd".

        Returns:
            Tuple of (pid, process_name)
        """
        if not pid_name:
            return (None, None)

        if "/" in pid_name:
            parts = pid_name.split("/", 1)
            try:
                pid = int(parts[0])
                return (pid, parts[1])
            except ValueError:
                return (None, pid_name)

        # Try to parse as just a PID
        try:
            pid = int(pid_name)
            return (pid, None)
        except ValueError:
            return (None, pid_name)

    def _normalize_state(self, state: str) -> str:
        """Normalize connection state across platforms."""
        state_upper = state.upper()

        # Normalize LISTENING to LISTEN
        if state_upper in ("LISTENING", "LISTEN"):
            return "LISTEN"

        # Standard states
        if state_upper in ("ESTABLISHED", "TIME_WAIT", "CLOSE_WAIT", "FIN_WAIT1", "FIN_WAIT2", "SYN_RECV"):
            return state_upper

        # Handle other variations
        if state_upper == "CLOSED":
            return "CLOSED"

        return state_upper if state_upper else "UNKNOWN"

"""Tests for Netstat parser."""

from pathlib import Path

from parsers.netstat import NetstatParser


REPO_ROOT = Path(__file__).resolve().parents[2]
NETSTAT_LINUX_SAMPLE = (REPO_ROOT / "samples" / "netstat_linux.txt").read_text()


class TestNetstatParserFormatDetection:
    """Test netstat format detection."""

    def test_detect_linux_format(self):
        parser = NetstatParser()
        data = "Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name"
        assert parser.detect_format(data) == "linux"

    def test_detect_macos_format(self):
        parser = NetstatParser()
        data = "Proto Recv-Q Send-Q  Local Address          Foreign Address        (state)"
        assert parser.detect_format(data) == "macos"

    def test_detect_windows_format(self):
        parser = NetstatParser()
        data = "Proto  Local Address          Foreign Address        State           PID"
        assert parser.detect_format(data) == "windows"


class TestNetstatParserParse:
    """Test parsing netstat formats."""

    def test_parse_linux(self):
        parser = NetstatParser()
        result = parser.parse(NETSTAT_LINUX_SAMPLE, platform="linux")
        assert result.success is True
        assert len(result.connections) == 4

        first = result.connections[0]
        assert first.local_ip == "0.0.0.0"
        assert first.local_port == 22
        assert first.state == "LISTEN"
        assert first.pid == 1234
        assert first.process_name == "sshd"

        second = result.connections[1]
        assert second.remote_ip == "10.0.0.5"
        assert second.remote_port == 54321
        assert second.state == "ESTABLISHED"

        udp = result.connections[3]
        assert udp.protocol == "udp"
        assert udp.pid == 2345
        assert udp.process_name == "dhclient"
        assert udp.state == "UNKNOWN"

    def test_parse_macos(self):
        parser = NetstatParser()
        data = """Active Internet connections (including servers)
Proto Recv-Q Send-Q  Local Address          Foreign Address        (state)
tcp4       0      0  *.22                   *.*                    LISTEN
udp4       0      0  192.168.1.10.68        *.*
"""
        result = parser.parse(data, platform="macos")
        assert result.success is True
        assert len(result.connections) == 2

        first = result.connections[0]
        assert first.local_ip == "0.0.0.0"
        assert first.local_port == 22
        assert first.state == "LISTEN"

        second = result.connections[1]
        assert second.protocol == "udp"
        assert second.state == "UNKNOWN"

    def test_parse_windows(self):
        parser = NetstatParser()
        data = """Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:22             0.0.0.0:0              LISTENING       1234
  TCP    [::]:80                [::]:0                 LISTENING       9012
  TCP    192.168.1.10:443       10.0.0.5:54321         ESTABLISHED     5678
  UDP    0.0.0.0:68             *:*                                    2345
"""
        result = parser.parse(data, platform="windows")
        assert result.success is True
        assert len(result.connections) == 4

        ipv6 = result.connections[1]
        assert ipv6.local_ip == "::"
        assert ipv6.local_port == 80
        assert ipv6.state == "LISTEN"

        udp = result.connections[3]
        assert udp.protocol == "udp"
        assert udp.pid == 2345
        assert udp.state == "UNKNOWN"

    def test_parse_empty_input(self):
        parser = NetstatParser()
        result = parser.parse("")
        assert result.success is False
        assert result.errors

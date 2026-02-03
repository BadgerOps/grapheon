"""Tests for Ping parser."""

from parsers.ping import PingParser


class TestPingParserFormatDetection:
    """Test ping format detection."""

    def test_detect_iplist_format(self):
        parser = PingParser()
        data = """# Alive hosts
192.168.1.1
10.0.0.5
"""
        assert parser.detect_format(data) == "iplist"

    def test_detect_fping_format(self):
        parser = PingParser()
        data = "192.168.1.1 is alive"
        assert parser.detect_format(data) == "fping"

    def test_detect_nmap_format(self):
        parser = PingParser()
        data = "Nmap scan report for 192.168.1.1"
        assert parser.detect_format(data) == "nmap"

    def test_detect_standard_format(self):
        parser = PingParser()
        data = "PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data."
        assert parser.detect_format(data) == "standard"

    def test_detect_unknown_format(self):
        parser = PingParser()
        data = "this is not ping output"
        assert parser.detect_format(data) is None


class TestPingParserParse:
    """Test parsing of ping formats."""

    def test_parse_iplist(self):
        parser = PingParser()
        data = """# Alive hosts
192.168.1.1
not-an-ip
10.0.0.5
"""
        result = parser.parse(data, format_hint="iplist")
        assert result.success is True
        assert len(result.hosts) == 2
        assert result.hosts[0].ip_address == "192.168.1.1"
        assert result.hosts[1].ip_address == "10.0.0.5"

    def test_parse_fping(self):
        parser = PingParser()
        data = """192.168.1.1 is alive
192.168.1.2 is unreachable
host.local is alive
192.168.1.10 is alive (25.3 ms)
"""
        result = parser.parse(data, format_hint="fping")
        assert result.success is True
        assert len(result.hosts) == 2
        assert {h.ip_address for h in result.hosts} == {"192.168.1.1", "192.168.1.10"}

    def test_parse_nmap_ping(self):
        parser = PingParser()
        data = """Starting Nmap
Nmap scan report for router.local (192.168.1.1)
Host is up (0.0012s latency).
MAC Address: 00:11:22:33:44:55 (Cisco Systems)
Nmap scan report for 192.168.1.5
Host is up (0.0023s latency).
Nmap done: 256 IP addresses (2 hosts up) scanned in 2.45 seconds
"""
        result = parser.parse(data, format_hint="nmap")
        assert result.success is True
        assert len(result.hosts) == 2

        host1 = result.hosts[0]
        assert host1.ip_address == "192.168.1.1"
        assert host1.hostname == "router.local"
        assert host1.mac_address == "00:11:22:33:44:55"
        assert host1.vendor == "Cisco Systems"

        host2 = result.hosts[1]
        assert host2.ip_address == "192.168.1.5"
        assert host2.hostname is None

    def test_parse_standard_ping(self):
        parser = PingParser()
        data = """PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.
64 bytes from 8.8.8.8: icmp_seq=1 ttl=118 time=10.2 ms
64 bytes from 8.8.8.8: icmp_seq=2 ttl=118 time=10.3 ms

--- 8.8.8.8 ping statistics ---
2 packets transmitted, 2 received, 0% packet loss, time 1001ms
rtt min/avg/max/mdev = 10.200/10.250/10.300/0.050 ms
"""
        result = parser.parse(data, format_hint="standard")
        assert result.success is True
        assert len(result.hosts) == 1
        assert result.hosts[0].ip_address == "8.8.8.8"

    def test_parse_empty_input(self):
        parser = PingParser()
        result = parser.parse("")
        assert result.success is False
        assert result.errors

    def test_parse_unknown_format(self):
        parser = PingParser()
        result = parser.parse("not a ping format")
        assert result.success is False
        assert result.errors

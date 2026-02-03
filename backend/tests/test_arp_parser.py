"""Tests for ARP parser."""

from parsers.arp import ArpParser


class TestArpParserFormatDetection:
    """Test ARP format detection."""

    def test_detect_linux_format(self):
        parser = ArpParser()
        data = "router (192.168.1.1) at 00:11:22:33:44:55 [ether] on eth0"
        assert parser.detect_format(data) == "linux"

    def test_detect_macos_format(self):
        parser = ArpParser()
        data = "? (192.168.1.1) at 0:11:22:33:44:55 on en0 ifscope [ethernet]"
        assert parser.detect_format(data) == "macos"

    def test_detect_windows_format(self):
        parser = ArpParser()
        data = "Interface: 192.168.1.100 --- 0x4\n  Internet Address      Physical Address      Type"
        assert parser.detect_format(data) == "windows"


class TestArpParserParse:
    """Test parsing ARP formats."""

    def test_parse_linux(self):
        parser = ArpParser()
        data = """router (192.168.1.1) at 00:11:22:33:44:55 [ether] on eth0
server (192.168.1.10) at aa:bb:cc:dd:ee:ff [ether] on eth0
? (192.168.1.20) at <incomplete> on eth0
"""
        result = parser.parse(data, platform="linux")
        assert result.success is True
        assert len(result.arp_entries) == 3
        assert result.arp_entries[0].mac_address == "00:11:22:33:44:55"
        assert result.arp_entries[2].mac_address is None

    def test_parse_linux_ip_neigh(self):
        parser = ArpParser()
        data = """192.168.1.1 dev eth0 lladdr 00:11:22:33:44:55 REACHABLE
192.168.1.10 dev eth0 lladdr aa:bb:cc:dd:ee:ff STALE
192.168.1.20 dev eth0  FAILED
"""
        result = parser.parse(data, platform="linux")
        assert result.success is True
        assert len(result.arp_entries) == 3
        assert result.arp_entries[2].mac_address is None
        assert result.arp_entries[2].entry_type == "failed"

    def test_parse_macos(self):
        parser = ArpParser()
        data = """? (192.168.1.1) at 0:11:22:33:44:55 on en0 ifscope [ethernet]
? (192.168.1.10) at aa:bb:cc:dd:ee:ff on en0 ifscope [ethernet]
? (192.168.1.20) at (incomplete) on en0 ifscope [ethernet]
"""
        result = parser.parse(data, platform="macos")
        assert result.success is True
        assert len(result.arp_entries) == 3
        assert result.arp_entries[0].mac_address == "00:11:22:33:44:55"
        assert result.arp_entries[2].mac_address is None

    def test_parse_windows(self):
        parser = ArpParser()
        data = """Interface: 192.168.1.100 --- 0x4
  Internet Address      Physical Address      Type
  192.168.1.1           00-11-22-33-44-55     dynamic
  192.168.1.10          aa-bb-cc-dd-ee-ff     dynamic
  192.168.1.255         ff-ff-ff-ff-ff-ff     static
"""
        result = parser.parse(data, platform="windows")
        assert result.success is True
        assert len(result.arp_entries) == 3
        assert result.arp_entries[0].mac_address == "00:11:22:33:44:55"
        assert result.arp_entries[2].entry_type == "static"
        assert result.arp_entries[0].interface == "192.168.1.100"

    def test_mac_normalization_edge_case(self):
        parser = ArpParser()
        data = """Interface: 192.168.1.100 --- 0x4
  Internet Address      Physical Address      Type
  192.168.1.1           0-1-2-3-4-5           dynamic
"""
        result = parser.parse(data, platform="windows")
        assert result.success is True
        assert result.arp_entries[0].mac_address == "00:01:02:03:04:05"

    def test_parse_empty_input(self):
        parser = ArpParser()
        result = parser.parse("")
        assert result.success is False
        assert result.errors

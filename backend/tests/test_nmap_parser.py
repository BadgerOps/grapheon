"""Tests for NMAP parser."""

import pytest
from parsers.nmap import NmapParser


class TestNmapParserFormatDetection:
    """Test NMAP format detection."""

    def test_detect_xml_format(self):
        """Test detection of XML format."""
        parser = NmapParser()
        xml_data = "<?xml version=\"1.0\"?>\n<nmaprun>"
        assert parser.detect_format(xml_data) == "xml"

    def test_detect_xml_format_without_declaration(self):
        """Test detection of XML format without XML declaration."""
        parser = NmapParser()
        xml_data = "<nmaprun></nmaprun>"
        assert parser.detect_format(xml_data) == "xml"

    def test_detect_grep_format(self):
        """Test detection of greppable format."""
        parser = NmapParser()
        grep_data = "Host: 192.168.1.1 (router.local)\tPorts: 22/open/tcp//ssh///"
        assert parser.detect_format(grep_data) == "grep"

    def test_detect_unknown_format(self):
        """Test detection of unknown format."""
        parser = NmapParser()
        unknown_data = "This is not nmap output"
        assert parser.detect_format(unknown_data) is None


class TestNmapParserXML:
    """Test NMAP XML parser."""

    @pytest.fixture
    def xml_sample(self):
        """Sample NMAP XML output."""
        return """<?xml version="1.0"?>
<nmaprun scanner="nmap" args="nmap -sV -O 192.168.1.0/24" start="1675296000" version="7.92">
<host><status state="up"/>
<address addr="192.168.1.1" addrtype="ipv4"/>
<address addr="00:11:22:33:44:55" addrtype="mac" vendor="Cisco Systems"/>
<hostnames><hostname name="router.local" type="PTR"/></hostnames>
<ports>
<port protocol="tcp" portid="22"><state state="open"/><service name="ssh" product="OpenSSH" version="8.9p1" conf="10"/></port>
<port protocol="tcp" portid="80"><state state="open"/><service name="http" product="nginx" version="1.18.0" conf="10"/></port>
<port protocol="tcp" portid="443"><state state="open"/><service name="https" product="nginx" version="1.18.0" extrainfo="(Debian)" conf="10"/></port>
</ports>
<os><osmatch name="Linux 5.4 - 5.14" accuracy="95"/></os>
</host>
<host><status state="up"/>
<address addr="192.168.1.100" addrtype="ipv4"/>
<address addr="AA:BB:CC:DD:EE:FF" addrtype="mac" vendor="Apple"/>
<hostnames><hostname name="macbook.local" type="PTR"/></hostnames>
<ports>
<port protocol="tcp" portid="22"><state state="open"/><service name="ssh" product="OpenSSH" version="7.9" conf="10"/></port>
<port protocol="tcp" portid="5900"><state state="filtered"/><service name="vnc" product="RealVNC" version="6.7" conf="8"/></port>
</ports>
<os><osmatch name="Mac OS X 10.12 - 11.6" accuracy="92"/></os>
</host>
</nmaprun>"""

    def test_parse_xml_success(self, xml_sample):
        """Test successful XML parsing."""
        parser = NmapParser()
        result = parser.parse(xml_sample, format_hint="xml")

        assert result.success is True
        assert result.source_type == "nmap"
        assert len(result.hosts) == 2
        assert len(result.errors) == 0

    def test_parse_xml_first_host(self, xml_sample):
        """Test parsing first host from XML."""
        parser = NmapParser()
        result = parser.parse(xml_sample, format_hint="xml")

        host = result.hosts[0]
        assert host.ip_address == "192.168.1.1"
        assert host.mac_address == "00:11:22:33:44:55"
        assert host.vendor == "Cisco Systems"
        assert host.hostname == "router.local"
        assert host.os_name == "Linux 5.4 - 5.14"
        assert host.os_family == "linux"
        assert host.os_confidence == 95

    def test_parse_xml_ports(self, xml_sample):
        """Test parsing ports from XML."""
        parser = NmapParser()
        result = parser.parse(xml_sample, format_hint="xml")

        host = result.hosts[0]
        assert len(host.ports) == 3

        # Check SSH port
        ssh_port = next((p for p in host.ports if p.port_number == 22), None)
        assert ssh_port is not None
        assert ssh_port.protocol == "tcp"
        assert ssh_port.state == "open"
        assert ssh_port.service_name == "ssh"
        assert ssh_port.service_product == "OpenSSH"
        assert ssh_port.service_version == "8.9p1"
        assert ssh_port.confidence == 10

        # Check HTTP port
        http_port = next((p for p in host.ports if p.port_number == 80), None)
        assert http_port is not None
        assert http_port.state == "open"
        assert http_port.service_name == "http"

        # Check HTTPS port with extra info
        https_port = next((p for p in host.ports if p.port_number == 443), None)
        assert https_port is not None
        assert https_port.service_banner == "(Debian)"

    def test_parse_xml_second_host(self, xml_sample):
        """Test parsing second host from XML."""
        parser = NmapParser()
        result = parser.parse(xml_sample, format_hint="xml")

        host = result.hosts[1]
        assert host.ip_address == "192.168.1.100"
        assert host.vendor == "Apple"
        assert host.os_family == "macos"
        assert len(host.ports) == 2

        # Check filtered port
        vnc_port = next((p for p in host.ports if p.port_number == 5900), None)
        assert vnc_port is not None
        assert vnc_port.state == "filtered"

    def test_parse_xml_malformed(self):
        """Test parsing malformed XML."""
        parser = NmapParser()
        malformed_xml = "<?xml version=\"1.0\"?>\n<nmaprun><host>"
        result = parser.parse(malformed_xml, format_hint="xml")

        assert result.success is False
        assert len(result.errors) > 0

    def test_parse_xml_empty_input(self):
        """Test parsing empty input."""
        parser = NmapParser()
        result = parser.parse("", format_hint="xml")

        assert result.success is False
        assert "Empty input" in result.errors[0]

    def test_parse_xml_no_hosts(self):
        """Test parsing XML with no hosts."""
        parser = NmapParser()
        xml_no_hosts = "<?xml version=\"1.0\"?>\n<nmaprun></nmaprun>"
        result = parser.parse(xml_no_hosts, format_hint="xml")

        assert result.success is True
        assert len(result.hosts) == 0
        assert len(result.warnings) > 0


class TestNmapParserGrep:
    """Test NMAP greppable format parser."""

    @pytest.fixture
    def grep_sample(self):
        """Sample NMAP greppable output."""
        return """# Nmap 7.92 scan initiated
Host: 192.168.1.1 (router.local)	Ports: 22/open/tcp//ssh/OpenSSH 8.9///,80/open/tcp//http/nginx 1.18///,443/open/tcp//https/nginx 1.18/(Debian)/	OS: Linux 5.4 - 5.14	MAC: 00:11:22:33:44:55 (Cisco Systems)
Host: 192.168.1.100 ()	Ports: 22/open/tcp//ssh/OpenSSH 7.9///,5900/filtered/tcp//vnc/RealVNC 6.7//	OS: Mac OS X 10.12 - 11.6	MAC: AA:BB:CC:DD:EE:FF (Apple)
Host: 192.168.1.50 (server.local)	Ports: 3306/open/tcp//mysql/MySQL 5.7.22///	OS: Linux	MAC: 11:22:33:44:55:66 (Dell)
# Nmap done"""

    def test_parse_grep_success(self, grep_sample):
        """Test successful grep parsing."""
        parser = NmapParser()
        result = parser.parse(grep_sample, format_hint="grep")

        assert result.success is True
        assert result.source_type == "nmap"
        assert len(result.hosts) == 3
        assert len(result.errors) == 0

    def test_parse_grep_first_host(self, grep_sample):
        """Test parsing first host from grep output."""
        parser = NmapParser()
        result = parser.parse(grep_sample, format_hint="grep")

        host = result.hosts[0]
        assert host.ip_address == "192.168.1.1"
        assert host.hostname == "router.local"
        assert host.mac_address == "00:11:22:33:44:55"
        assert host.vendor == "Cisco Systems"
        assert host.os_name == "Linux 5.4 - 5.14"
        assert host.os_family == "linux"

    def test_parse_grep_ports(self, grep_sample):
        """Test parsing ports from grep output."""
        parser = NmapParser()
        result = parser.parse(grep_sample, format_hint="grep")

        host = result.hosts[0]
        assert len(host.ports) == 3

        # Check SSH port
        ssh_port = next((p for p in host.ports if p.port_number == 22), None)
        assert ssh_port is not None
        assert ssh_port.protocol == "tcp"
        assert ssh_port.state == "open"
        assert ssh_port.service_name == "ssh"
        assert ssh_port.service_product == "OpenSSH"
        assert ssh_port.service_version == "8.9"

        # Check HTTPS port with banner
        https_port = next((p for p in host.ports if p.port_number == 443), None)
        assert https_port is not None
        assert https_port.service_banner == "(Debian)"

    def test_parse_grep_no_hostname(self, grep_sample):
        """Test parsing host with no hostname from grep."""
        parser = NmapParser()
        result = parser.parse(grep_sample, format_hint="grep")

        host = result.hosts[1]
        assert host.ip_address == "192.168.1.100"
        assert host.hostname is None

    def test_parse_grep_macos_detection(self, grep_sample):
        """Test macOS OS family detection."""
        parser = NmapParser()
        result = parser.parse(grep_sample, format_hint="grep")

        host = result.hosts[1]
        assert host.os_family == "macos"

    def test_parse_grep_filtered_port(self, grep_sample):
        """Test parsing filtered port."""
        parser = NmapParser()
        result = parser.parse(grep_sample, format_hint="grep")

        host = result.hosts[1]
        vnc_port = next((p for p in host.ports if p.port_number == 5900), None)
        assert vnc_port is not None
        assert vnc_port.state == "filtered"

    def test_parse_grep_ignores_comments(self, grep_sample):
        """Test that grep parser ignores comments."""
        parser = NmapParser()
        result = parser.parse(grep_sample, format_hint="grep")

        # Should only have 3 hosts (comments ignored)
        assert len(result.hosts) == 3

    def test_parse_grep_auto_detect(self, grep_sample):
        """Test auto-detection of grep format."""
        parser = NmapParser()
        result = parser.parse(grep_sample)

        assert result.success is True
        assert len(result.hosts) == 3


class TestNmapParserAutoDetect:
    """Test auto-detection of format."""

    def test_auto_detect_xml(self):
        """Test auto-detection of XML format."""
        parser = NmapParser()
        xml_data = """<?xml version="1.0"?>
<nmaprun>
<host><status state="up"/>
<address addr="10.0.0.1" addrtype="ipv4"/>
</host>
</nmaprun>"""
        result = parser.parse(xml_data)
        assert result.success is True
        assert len(result.hosts) == 1

    def test_auto_detect_grep(self):
        """Test auto-detection of grep format."""
        parser = NmapParser()
        grep_data = "Host: 10.0.0.1 (test.local)\tPorts: 22/open/tcp//ssh///"
        result = parser.parse(grep_data)
        assert result.success is True
        assert len(result.hosts) == 1


class TestNmapParserOSDetection:
    """Test OS family detection."""

    def test_detect_linux(self):
        """Test Linux detection."""
        parser = NmapParser()
        assert parser._infer_os_family("Ubuntu 20.04") == "linux"
        assert parser._infer_os_family("Debian GNU/Linux 11") == "linux"
        assert parser._infer_os_family("CentOS 7.9") == "linux"
        assert parser._infer_os_family("Red Hat Enterprise Linux 8") == "linux"
        assert parser._infer_os_family("Fedora 35") == "linux"

    def test_detect_windows(self):
        """Test Windows detection."""
        parser = NmapParser()
        assert parser._infer_os_family("Microsoft Windows 10") == "windows"
        assert parser._infer_os_family("Windows Server 2019") == "windows"

    def test_detect_macos(self):
        """Test macOS detection."""
        parser = NmapParser()
        assert parser._infer_os_family("Mac OS X 10.15") == "macos"
        assert parser._infer_os_family("macOS 11.6") == "macos"

    def test_detect_network_devices(self):
        """Test network device detection."""
        parser = NmapParser()
        assert parser._infer_os_family("Cisco IOS 15.2") == "network"
        assert parser._infer_os_family("Juniper JunOS") == "network"
        assert parser._infer_os_family("OpenWrt Router") == "network"

    def test_detect_unknown(self):
        """Test unknown OS detection."""
        parser = NmapParser()
        assert parser._infer_os_family("Unknown OS") == "unknown"
        assert parser._infer_os_family("") == "unknown"
        assert parser._infer_os_family(None) == "unknown"


class TestNmapParserEdgeCases:
    """Test edge cases."""

    def test_ipv6_address(self):
        """Test parsing IPv6 addresses."""
        parser = NmapParser()
        xml_data = """<?xml version="1.0"?>
<nmaprun>
<host><status state="up"/>
<address addr="2001:db8::1" addrtype="ipv6"/>
</host>
</nmaprun>"""
        result = parser.parse(xml_data, format_hint="xml")
        assert result.success is True
        assert result.hosts[0].ip_address == "2001:db8::1"

    def test_host_without_mac(self):
        """Test parsing host without MAC address."""
        parser = NmapParser()
        xml_data = """<?xml version="1.0"?>
<nmaprun>
<host><status state="up"/>
<address addr="10.0.0.1" addrtype="ipv4"/>
</host>
</nmaprun>"""
        result = parser.parse(xml_data, format_hint="xml")
        assert result.success is True
        assert result.hosts[0].mac_address is None

    def test_host_without_ports(self):
        """Test parsing host without any ports."""
        parser = NmapParser()
        xml_data = """<?xml version="1.0"?>
<nmaprun>
<host><status state="up"/>
<address addr="10.0.0.1" addrtype="ipv4"/>
</host>
</nmaprun>"""
        result = parser.parse(xml_data, format_hint="xml")
        assert result.success is True
        assert len(result.hosts[0].ports) == 0

    def test_host_without_os(self):
        """Test parsing host without OS detection."""
        parser = NmapParser()
        xml_data = """<?xml version="1.0"?>
<nmaprun>
<host><status state="up"/>
<address addr="10.0.0.1" addrtype="ipv4"/>
</host>
</nmaprun>"""
        result = parser.parse(xml_data, format_hint="xml")
        assert result.success is True
        assert result.hosts[0].os_name is None
        assert result.hosts[0].os_family is None

    def test_port_without_service_info(self):
        """Test parsing port without service information."""
        parser = NmapParser()
        xml_data = """<?xml version="1.0"?>
<nmaprun>
<host><status state="up"/>
<address addr="10.0.0.1" addrtype="ipv4"/>
<ports>
<port protocol="tcp" portid="22"><state state="closed"/></port>
</ports>
</host>
</nmaprun>"""
        result = parser.parse(xml_data, format_hint="xml")
        assert result.success is True
        port = result.hosts[0].ports[0]
        assert port.port_number == 22
        assert port.state == "closed"
        assert port.service_name is None

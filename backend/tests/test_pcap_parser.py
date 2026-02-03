"""Tests for PCAP parser fallback behavior."""

from parsers.pcap import PcapParser


def test_detect_format_pcap_magic():
    parser = PcapParser()
    data = b"\xd4\xc3\xb2\xa1" + b"\x00" * 10
    assert parser.detect_format(data) == "pcap"


def test_detect_format_pcapng_magic():
    parser = PcapParser()
    data = b"\x0a\x0d\x0d\x0a" + b"\x00" * 10
    assert parser.detect_format(data) == "pcapng"


def test_tcpdump_fallback_parsing():
    parser = PcapParser()
    parser._scapy_available = False

    tcpdump_text = """10:30:45.123456 IP 192.168.1.100.443 > 10.0.0.1.54321: Flags [S], seq 0, win 65535
10:30:45.223456 IP 10.0.0.1.54321 > 192.168.1.100.443: Flags [S.], seq 0, win 65535
10:30:46.123456 IP 10.0.0.2.5353 > 224.0.0.251.5353: UDP, length 32
"""

    result = parser.parse(tcpdump_text)

    assert result.success is True
    assert len(result.hosts) >= 3
    assert any(conn.protocol == "tcp" for conn in result.connections)
    assert any(conn.protocol == "udp" for conn in result.connections)

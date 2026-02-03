"""Tests for Traceroute parser."""

from parsers.traceroute import TracerouteParser


class TestTracerouteParserFormatDetection:
    """Test traceroute format detection."""

    def test_detect_linux_format(self):
        parser = TracerouteParser()
        data = "traceroute to example.com (93.184.216.34), 30 hops max"
        assert parser.detect_format(data) == "linux"

    def test_detect_windows_format(self):
        parser = TracerouteParser()
        data = "Tracing route to example.com [93.184.216.34]"
        assert parser.detect_format(data) == "windows"

    def test_detect_mtr_format(self):
        parser = TracerouteParser()
        data = "1.|-- 192.168.1.1  0.0%  10  1.2  1.3  1.1  1.5  0.1\nLoss%"
        assert parser.detect_format(data) == "mtr"

    def test_detect_unknown_format(self):
        parser = TracerouteParser()
        data = "this is not traceroute"
        assert parser.detect_format(data) is None


class TestTracerouteParserParse:
    """Test parsing traceroute formats."""

    def test_parse_linux(self):
        parser = TracerouteParser()
        data = """traceroute to example.com (93.184.216.34), 30 hops max
 1  router.local (192.168.1.1)  1.123 ms  1.234 ms  1.345 ms
 2  10.0.0.1 (10.0.0.1)  5.678 ms  5.432 ms  5.789 ms
 3  * * *
"""
        result = parser.parse(data, format_hint="linux")
        assert result.success is True
        assert len(result.route_hops) == 3

        hop1 = result.route_hops[0]
        assert hop1.hop_number == 1
        assert hop1.hostname == "router.local"
        assert hop1.ip_address == "192.168.1.1"
        assert hop1.rtt_ms[:1] == [1.123]

        hop3 = result.route_hops[2]
        assert hop3.hop_number == 3
        assert hop3.ip_address is None
        assert hop3.rtt_ms == []

    def test_parse_windows(self):
        parser = TracerouteParser()
        data = """Tracing route to example.com [93.184.216.34]
over a maximum of 30 hops:

  1     1 ms     2 ms     3 ms  router.local [192.168.1.1]
  2     *        *        *     Request timed out.
  3     10 ms    11 ms    12 ms  93.184.216.34

Trace complete.
"""
        result = parser.parse(data, format_hint="windows")
        assert result.success is True
        assert len(result.route_hops) == 3

        hop1 = result.route_hops[0]
        assert hop1.ip_address == "192.168.1.1"
        assert hop1.hostname == "router.local"
        assert hop1.rtt_ms == [1.0, 2.0, 3.0]

        hop2 = result.route_hops[1]
        assert hop2.ip_address is None
        assert hop2.rtt_ms == []

        hop3 = result.route_hops[2]
        assert hop3.ip_address == "93.184.216.34"

    def test_parse_mtr(self):
        parser = TracerouteParser()
        data = """HOST: local                                      Loss%   Snt   Last   Avg  Best  Wrst StDev
  1.|-- 192.168.1.1                               0.0%    10    1.2   1.3   1.1   1.5   0.1
  2.|-- example.com                               0.0%    10   10.5  10.7  10.4  11.0   0.2
"""
        result = parser.parse(data, format_hint="mtr")
        assert result.success is True
        assert len(result.route_hops) == 2

        hop1 = result.route_hops[0]
        assert hop1.ip_address == "192.168.1.1"
        assert hop1.rtt_ms[:1] == [1.2]

        hop2 = result.route_hops[1]
        assert hop2.hostname == "example.com"
        assert hop2.ip_address is None

    def test_parse_empty_input(self):
        parser = TracerouteParser()
        result = parser.parse("")
        assert result.success is False
        assert result.errors

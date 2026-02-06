"""
Comprehensive tests for all Pydantic schema validators.

Tests cover both valid and invalid inputs for:
- HostBase and HostUpdate
- PortBase and PortUpdate
- ConnectionBase
- ARPEntryBase
- RawImportBase
- DeviceIdentityBase and DeviceIdentityUpdate
"""

import pytest
from pydantic import ValidationError

from schemas import (
    HostBase, HostUpdate, PortBase, PortUpdate, ConnectionBase, ARPEntryBase, RawImportBase, DeviceIdentityBase, DeviceIdentityUpdate,
)


# ============================================================================
# HostBase and HostCreate Tests
# ============================================================================

class TestHostBaseIPAddress:
    """Test IP address validation for HostBase."""

    def test_valid_ipv4(self):
        """Valid IPv4 address should be accepted."""
        host = HostBase(ip_address="192.168.1.1")
        assert host.ip_address == "192.168.1.1"

    def test_valid_ipv6(self):
        """Valid IPv6 address should be accepted."""
        host = HostBase(ip_address="2001:db8::1")
        assert host.ip_address == "2001:db8::1"

    def test_ipv4_edge_cases(self):
        """Test edge case IPv4 addresses."""
        # Localhost
        host = HostBase(ip_address="127.0.0.1")
        assert host.ip_address == "127.0.0.1"
        
        # Broadcast
        host = HostBase(ip_address="255.255.255.255")
        assert host.ip_address == "255.255.255.255"
        
        # First address
        host = HostBase(ip_address="0.0.0.1")
        assert host.ip_address == "0.0.0.1"

    def test_ipv6_full_format(self):
        """Test full IPv6 format."""
        host = HostBase(ip_address="2001:0db8:0000:0000:0000:0000:0000:0001")
        assert host.ip_address == "2001:0db8:0000:0000:0000:0000:0000:0001"

    def test_ipv6_compressed_format(self):
        """Test compressed IPv6 format."""
        host = HostBase(ip_address="fe80::1")
        assert host.ip_address == "fe80::1"

    def test_invalid_ipv4_format(self):
        """Invalid IPv4 format should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            HostBase(ip_address="256.256.256.256")
        assert "Invalid IP address" in str(exc_info.value)

    def test_invalid_ip_non_numeric(self):
        """Non-numeric IP should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            HostBase(ip_address="not.an.ip.address")
        assert "Invalid IP address" in str(exc_info.value)

    def test_invalid_ip_partial(self):
        """Partial IP should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            HostBase(ip_address="192.168.1")
        assert "Invalid IP address" in str(exc_info.value)

    def test_unspecified_ipv4_rejected(self):
        """Unspecified IPv4 (0.0.0.0) should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            HostBase(ip_address="0.0.0.0")
        assert "Unspecified" in str(exc_info.value)

    def test_unspecified_ipv6_rejected(self):
        """Unspecified IPv6 (::) should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            HostBase(ip_address="::")
        assert "Unspecified" in str(exc_info.value)

    def test_empty_ip(self):
        """Empty IP string should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            HostBase(ip_address="")
        assert "Invalid IP address" in str(exc_info.value)


class TestHostBaseMACAddress:
    """Test MAC address validation for HostBase."""

    def test_valid_mac_colon_format(self):
        """Valid MAC with colon separator should be accepted."""
        host = HostBase(ip_address="192.168.1.1", mac_address="00:1A:2B:3C:4D:5E")
        assert host.mac_address == "00:1A:2B:3C:4D:5E"

    def test_valid_mac_dash_format(self):
        """Valid MAC with dash separator should be accepted."""
        host = HostBase(ip_address="192.168.1.1", mac_address="00-1A-2B-3C-4D-5E")
        assert host.mac_address == "00-1A-2B-3C-4D-5E"

    def test_valid_mac_uppercase(self):
        """Valid MAC in uppercase should be accepted."""
        host = HostBase(ip_address="192.168.1.1", mac_address="FF:FF:FF:FF:FF:FF")
        assert host.mac_address == "FF:FF:FF:FF:FF:FF"

    def test_valid_mac_lowercase(self):
        """Valid MAC in lowercase should be accepted."""
        host = HostBase(ip_address="192.168.1.1", mac_address="aa:bb:cc:dd:ee:ff")
        assert host.mac_address == "aa:bb:cc:dd:ee:ff"

    def test_valid_mac_mixed_case(self):
        """Valid MAC in mixed case should be accepted."""
        host = HostBase(ip_address="192.168.1.1", mac_address="Aa:Bb:Cc:Dd:Ee:Ff")
        assert host.mac_address == "Aa:Bb:Cc:Dd:Ee:Ff"

    def test_valid_mac_mixed_separators(self):
        """Valid MAC with mixed separators (colon and dash) should be accepted by regex."""
        host = HostBase(ip_address="192.168.1.1", mac_address="00:1A-2B:3C-4D:5E")
        assert host.mac_address == "00:1A-2B:3C-4D:5E"

    def test_mac_optional_field(self):
        """MAC address field should be optional (None)."""
        host = HostBase(ip_address="192.168.1.1", mac_address=None)
        assert host.mac_address is None

    def test_mac_not_provided(self):
        """MAC address not provided should default to None."""
        host = HostBase(ip_address="192.168.1.1")
        assert host.mac_address is None

    def test_invalid_mac_wrong_length(self):
        """MAC with wrong length should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            HostBase(ip_address="192.168.1.1", mac_address="00:1A:2B:3C:4D")
        assert "Invalid MAC address" in str(exc_info.value)

    def test_invalid_mac_invalid_chars(self):
        """MAC with invalid characters should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            HostBase(ip_address="192.168.1.1", mac_address="00:1A:2B:3C:4D:XY")
        assert "Invalid MAC address" in str(exc_info.value)

    def test_invalid_mac_no_separator(self):
        """MAC without separator should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            HostBase(ip_address="192.168.1.1", mac_address="001A2B3C4D5E")
        assert "Invalid MAC address" in str(exc_info.value)


class TestHostBaseHostname:
    """Test hostname validation for HostBase."""

    def test_valid_simple_hostname(self):
        """Simple alphanumeric hostname should be accepted."""
        host = HostBase(ip_address="192.168.1.1", hostname="router01")
        assert host.hostname == "router01"

    def test_valid_hostname_with_dots(self):
        """Hostname with dots should be accepted."""
        host = HostBase(ip_address="192.168.1.1", hostname="host.example.local")
        assert host.hostname == "host.example.local"

    def test_valid_hostname_with_hyphens(self):
        """Hostname with hyphens should be accepted."""
        host = HostBase(ip_address="192.168.1.1", hostname="my-server-01")
        assert host.hostname == "my-server-01"

    def test_valid_hostname_with_underscores(self):
        """Hostname with underscores should be accepted."""
        host = HostBase(ip_address="192.168.1.1", hostname="my_server_01")
        assert host.hostname == "my_server_01"

    def test_valid_hostname_mixed_separators(self):
        """Hostname with mixed separators should be accepted."""
        host = HostBase(ip_address="192.168.1.1", hostname="web-server_01.local")
        assert host.hostname == "web-server_01.local"

    def test_hostname_max_length(self):
        """Hostname at max length (255) should be accepted."""
        hostname = "a" * 255
        host = HostBase(ip_address="192.168.1.1", hostname=hostname)
        assert host.hostname == hostname

    def test_hostname_optional(self):
        """Hostname should be optional (None)."""
        host = HostBase(ip_address="192.168.1.1", hostname=None)
        assert host.hostname is None

    def test_hostname_too_long(self):
        """Hostname exceeding max length (255) should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            HostBase(ip_address="192.168.1.1", hostname="a" * 256)
        assert "too long" in str(exc_info.value).lower()

    def test_invalid_hostname_spaces(self):
        """Hostname with spaces should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            HostBase(ip_address="192.168.1.1", hostname="my server")
        assert "Invalid hostname" in str(exc_info.value)

    def test_invalid_hostname_special_chars(self):
        """Hostname with special characters should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            HostBase(ip_address="192.168.1.1", hostname="my@server!")
        assert "Invalid hostname" in str(exc_info.value)


class TestHostBaseFQDN:
    """Test FQDN validation for HostBase."""

    def test_valid_fqdn(self):
        """Valid FQDN should be accepted."""
        host = HostBase(ip_address="192.168.1.1", fqdn="server.example.com")
        assert host.fqdn == "server.example.com"

    def test_valid_fqdn_multiple_levels(self):
        """FQDN with multiple levels should be accepted."""
        host = HostBase(ip_address="192.168.1.1", fqdn="web.internal.company.example.com")
        assert host.fqdn == "web.internal.company.example.com"

    def test_fqdn_max_length(self):
        """FQDN at max length (255) should be accepted."""
        fqdn = "a" * 250 + ".com"  # 254 chars
        host = HostBase(ip_address="192.168.1.1", fqdn=fqdn)
        assert host.fqdn == fqdn

    def test_fqdn_optional(self):
        """FQDN should be optional (None)."""
        host = HostBase(ip_address="192.168.1.1", fqdn=None)
        assert host.fqdn is None

    def test_fqdn_too_long(self):
        """FQDN exceeding max length (255) should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            HostBase(ip_address="192.168.1.1", fqdn="a" * 256)
        assert "too long" in str(exc_info.value).lower()

    def test_invalid_fqdn_spaces(self):
        """FQDN with spaces should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            HostBase(ip_address="192.168.1.1", fqdn="server example.com")
        assert "Invalid FQDN" in str(exc_info.value)


class TestHostBaseDeviceType:
    """Test device_type validation for HostBase."""

    def test_valid_device_types(self):
        """All valid device types should be accepted."""
        valid_types = ["router", "switch", "firewall", "server", "workstation",
                      "printer", "iot", "phone", "storage", "virtual", "unknown"]
        for device_type in valid_types:
            host = HostBase(ip_address="192.168.1.1", device_type=device_type)
            assert host.device_type == device_type

    def test_device_type_case_normalized_upper(self):
        """Device type in uppercase should be normalized to lowercase."""
        host = HostBase(ip_address="192.168.1.1", device_type="ROUTER")
        assert host.device_type == "router"

    def test_device_type_case_normalized_mixed(self):
        """Device type in mixed case should be normalized to lowercase."""
        host = HostBase(ip_address="192.168.1.1", device_type="FiReWaLl")
        assert host.device_type == "firewall"

    def test_device_type_optional(self):
        """Device type should be optional (None)."""
        host = HostBase(ip_address="192.168.1.1", device_type=None)
        assert host.device_type is None

    def test_invalid_device_type(self):
        """Invalid device type should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            HostBase(ip_address="192.168.1.1", device_type="invalid_type")
        assert "Invalid device type" in str(exc_info.value)


class TestHostBaseOSFamily:
    """Test os_family validation for HostBase."""

    def test_valid_os_families(self):
        """All valid OS families should be accepted."""
        valid_os = ["linux", "windows", "macos", "ios", "android",
                   "unix", "bsd", "vmware", "unknown"]
        for os_family in valid_os:
            host = HostBase(ip_address="192.168.1.1", os_family=os_family)
            assert host.os_family == os_family

    def test_os_family_case_normalized(self):
        """OS family in uppercase should be normalized to lowercase."""
        host = HostBase(ip_address="192.168.1.1", os_family="WINDOWS")
        assert host.os_family == "windows"

    def test_os_family_optional(self):
        """OS family should be optional (None)."""
        host = HostBase(ip_address="192.168.1.1", os_family=None)
        assert host.os_family is None

    def test_invalid_os_family(self):
        """Invalid OS family should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            HostBase(ip_address="192.168.1.1", os_family="dos")
        assert "Invalid OS family" in str(exc_info.value)


class TestHostBaseCriticality:
    """Test criticality validation for HostBase."""

    def test_valid_criticalities(self):
        """All valid criticalities should be accepted."""
        valid_crit = ["critical", "high", "medium", "low"]
        for crit in valid_crit:
            host = HostBase(ip_address="192.168.1.1", criticality=crit)
            assert host.criticality == crit

    def test_criticality_case_normalized(self):
        """Criticality in uppercase should be normalized to lowercase."""
        host = HostBase(ip_address="192.168.1.1", criticality="CRITICAL")
        assert host.criticality == "critical"

    def test_criticality_optional(self):
        """Criticality should be optional (None)."""
        host = HostBase(ip_address="192.168.1.1", criticality=None)
        assert host.criticality is None

    def test_invalid_criticality(self):
        """Invalid criticality should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            HostBase(ip_address="192.168.1.1", criticality="extreme")
        assert "Invalid criticality" in str(exc_info.value)


class TestHostBaseOSConfidence:
    """Test os_confidence validation for HostBase."""

    def test_valid_os_confidence(self):
        """Valid OS confidence values (0-100) should be accepted."""
        for confidence in [0, 50, 100]:
            host = HostBase(ip_address="192.168.1.1", os_confidence=confidence)
            assert host.os_confidence == confidence

    def test_os_confidence_optional(self):
        """OS confidence should be optional (None)."""
        host = HostBase(ip_address="192.168.1.1", os_confidence=None)
        assert host.os_confidence is None

    def test_os_confidence_below_zero(self):
        """OS confidence below 0 should raise ValidationError."""
        with pytest.raises(ValidationError):
            HostBase(ip_address="192.168.1.1", os_confidence=-1)

    def test_os_confidence_above_100(self):
        """OS confidence above 100 should raise ValidationError."""
        with pytest.raises(ValidationError):
            HostBase(ip_address="192.168.1.1", os_confidence=101)


class TestHostBaseNotes:
    """Test notes field validation for HostBase."""

    def test_valid_notes(self):
        """Valid notes should be accepted."""
        notes = "This is a test host"
        host = HostBase(ip_address="192.168.1.1", notes=notes)
        assert host.notes == notes

    def test_notes_max_length(self):
        """Notes at max length (5000) should be accepted."""
        notes = "a" * 5000
        host = HostBase(ip_address="192.168.1.1", notes=notes)
        assert host.notes == notes

    def test_notes_optional(self):
        """Notes should be optional (None)."""
        host = HostBase(ip_address="192.168.1.1", notes=None)
        assert host.notes is None

    def test_notes_exceeds_max_length(self):
        """Notes exceeding max length (5000) should raise ValidationError."""
        with pytest.raises(ValidationError):
            HostBase(ip_address="192.168.1.1", notes="a" * 5001)

    def test_notes_empty_string(self):
        """Empty string notes should be accepted."""
        host = HostBase(ip_address="192.168.1.1", notes="")
        assert host.notes == ""


# ============================================================================
# HostUpdate Tests
# ============================================================================

class TestHostUpdateAllFieldsOptional:
    """Test that all fields in HostUpdate are optional."""

    def test_empty_host_update(self):
        """Creating HostUpdate with no fields should succeed."""
        update = HostUpdate()
        assert update.ip_address is None
        assert update.hostname is None
        assert update.device_type is None

    def test_host_update_single_field(self):
        """HostUpdate with single field should work."""
        update = HostUpdate(ip_address="192.168.1.1")
        assert update.ip_address == "192.168.1.1"
        assert update.hostname is None

    def test_host_update_multiple_fields(self):
        """HostUpdate with multiple fields should work."""
        update = HostUpdate(
            ip_address="192.168.1.1",
            hostname="server",
            device_type="router"
        )
        assert update.ip_address == "192.168.1.1"
        assert update.hostname == "server"
        assert update.device_type == "router"

    def test_host_update_validates_ip(self):
        """HostUpdate should validate IP address."""
        with pytest.raises(ValidationError) as exc_info:
            HostUpdate(ip_address="invalid.ip")
        assert "Invalid IP address" in str(exc_info.value)

    def test_host_update_validates_mac(self):
        """HostUpdate should validate MAC address."""
        with pytest.raises(ValidationError) as exc_info:
            HostUpdate(mac_address="invalid_mac")
        assert "Invalid MAC address" in str(exc_info.value)

    def test_host_update_validates_hostname(self):
        """HostUpdate should validate hostname."""
        with pytest.raises(ValidationError) as exc_info:
            HostUpdate(hostname="a" * 256)
        assert "too long" in str(exc_info.value).lower()

    def test_host_update_validates_device_type(self):
        """HostUpdate should validate device type."""
        with pytest.raises(ValidationError) as exc_info:
            HostUpdate(device_type="invalid")
        assert "Invalid device type" in str(exc_info.value)

    def test_host_update_none_passthrough(self):
        """HostUpdate should pass through None values."""
        update = HostUpdate(ip_address=None, hostname=None)
        assert update.ip_address is None
        assert update.hostname is None


# ============================================================================
# PortBase Tests
# ============================================================================

class TestPortBasePortNumber:
    """Test port_number validation for PortBase."""

    def test_valid_port_numbers(self):
        """Valid port numbers should be accepted."""
        for port in [0, 1, 22, 80, 443, 65535]:
            p = PortBase(port_number=port, protocol="tcp", state="open")
            assert p.port_number == port

    def test_port_number_below_zero(self):
        """Port number below 0 should raise ValidationError."""
        with pytest.raises(ValidationError):
            PortBase(port_number=-1, protocol="tcp", state="open")

    def test_port_number_above_65535(self):
        """Port number above 65535 should raise ValidationError."""
        with pytest.raises(ValidationError):
            PortBase(port_number=65536, protocol="tcp", state="open")


class TestPortBaseProtocol:
    """Test protocol validation for PortBase."""

    def test_valid_protocols(self):
        """All valid protocols should be accepted."""
        valid_protocols = ["tcp", "udp", "sctp", "ip"]
        for protocol in valid_protocols:
            p = PortBase(port_number=80, protocol=protocol, state="open")
            assert p.protocol == protocol

    def test_protocol_case_normalized(self):
        """Protocol in uppercase should be normalized to lowercase."""
        p = PortBase(port_number=80, protocol="TCP", state="open")
        assert p.protocol == "tcp"

    def test_protocol_case_normalized_mixed(self):
        """Protocol in mixed case should be normalized to lowercase."""
        p = PortBase(port_number=80, protocol="UdP", state="open")
        assert p.protocol == "udp"

    def test_invalid_protocol(self):
        """Invalid protocol should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            PortBase(port_number=80, protocol="http", state="open")
        assert "Invalid protocol" in str(exc_info.value)


class TestPortBaseState:
    """Test state validation for PortBase."""

    def test_valid_states(self):
        """All valid port states should be accepted."""
        valid_states = ["open", "closed", "filtered", "unfiltered"]
        for state in valid_states:
            p = PortBase(port_number=80, protocol="tcp", state=state)
            assert p.state == state

    def test_state_case_normalized(self):
        """State in uppercase should be normalized to lowercase."""
        p = PortBase(port_number=80, protocol="tcp", state="OPEN")
        assert p.state == "open"

    def test_state_case_normalized_mixed(self):
        """State in mixed case should be normalized to lowercase."""
        p = PortBase(port_number=80, protocol="tcp", state="FiLtErEd")
        assert p.state == "filtered"

    def test_invalid_state(self):
        """Invalid state should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            PortBase(port_number=80, protocol="tcp", state="half-open")
        assert "Invalid port state" in str(exc_info.value)


# ============================================================================
# PortUpdate Tests
# ============================================================================

class TestPortUpdateAllFieldsOptional:
    """Test that all fields in PortUpdate are optional."""

    def test_empty_port_update(self):
        """Creating PortUpdate with no fields should succeed."""
        update = PortUpdate()
        assert update.port_number is None
        assert update.protocol is None
        assert update.state is None

    def test_port_update_single_field(self):
        """PortUpdate with single field should work."""
        update = PortUpdate(port_number=80)
        assert update.port_number == 80
        assert update.protocol is None

    def test_port_update_validates_port_number(self):
        """PortUpdate should validate port number."""
        with pytest.raises(ValidationError):
            PortUpdate(port_number=70000)

    def test_port_update_validates_protocol(self):
        """PortUpdate should validate protocol."""
        with pytest.raises(ValidationError) as exc_info:
            PortUpdate(protocol="invalid")
        assert "Invalid protocol" in str(exc_info.value)

    def test_port_update_validates_state(self):
        """PortUpdate should validate state."""
        with pytest.raises(ValidationError) as exc_info:
            PortUpdate(state="invalid")
        assert "Invalid port state" in str(exc_info.value)


# ============================================================================
# ConnectionBase Tests
# ============================================================================

class TestConnectionBaseIPAddresses:
    """Test IP address validation for ConnectionBase."""

    def test_valid_connection(self):
        """Valid connection with both local and remote IPs should be accepted."""
        conn = ConnectionBase(
            local_ip="192.168.1.1",
            local_port=1234,
            remote_ip="8.8.8.8",
            protocol="tcp"
        )
        assert conn.local_ip == "192.168.1.1"
        assert conn.remote_ip == "8.8.8.8"

    def test_valid_ipv6_connection(self):
        """Valid connection with IPv6 addresses should be accepted."""
        conn = ConnectionBase(
            local_ip="2001:db8::1",
            local_port=1234,
            remote_ip="2001:db8::2",
            protocol="tcp"
        )
        assert conn.local_ip == "2001:db8::1"
        assert conn.remote_ip == "2001:db8::2"

    def test_invalid_local_ip(self):
        """Invalid local IP should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ConnectionBase(
                local_ip="invalid.ip",
                local_port=1234,
                remote_ip="8.8.8.8",
                protocol="tcp"
            )
        error_str = str(exc_info.value).lower()
        assert "invalid" in error_str and "ip" in error_str

    def test_invalid_remote_ip(self):
        """Invalid remote IP should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ConnectionBase(
                local_ip="192.168.1.1",
                local_port=1234,
                remote_ip="invalid.ip",
                protocol="tcp"
            )
        error_str = str(exc_info.value).lower()
        assert "invalid" in error_str and "ip" in error_str

    def test_unspecified_local_ip_allowed(self):
        """Unspecified local IP (0.0.0.0) is valid for connections (LISTEN state)."""
        conn = ConnectionBase(
            local_ip="0.0.0.0",
            local_port=1234,
            remote_ip="0.0.0.0",
            protocol="tcp"
        )
        assert conn.local_ip == "0.0.0.0"
        assert conn.remote_ip == "0.0.0.0"


class TestConnectionBasePorts:
    """Test port validation for ConnectionBase."""

    def test_valid_ports(self):
        """Valid local and remote ports should be accepted."""
        conn = ConnectionBase(
            local_ip="192.168.1.1",
            local_port=1234,
            remote_ip="8.8.8.8",
            remote_port=53,
            protocol="tcp"
        )
        assert conn.local_port == 1234
        assert conn.remote_port == 53

    def test_port_zero(self):
        """Port 0 should be accepted."""
        conn = ConnectionBase(
            local_ip="192.168.1.1",
            local_port=0,
            remote_ip="8.8.8.8",
            protocol="tcp"
        )
        assert conn.local_port == 0

    def test_port_max(self):
        """Port 65535 should be accepted."""
        conn = ConnectionBase(
            local_ip="192.168.1.1",
            local_port=65535,
            remote_ip="8.8.8.8",
            protocol="tcp"
        )
        assert conn.local_port == 65535

    def test_remote_port_optional(self):
        """Remote port should be optional (None)."""
        conn = ConnectionBase(
            local_ip="192.168.1.1",
            local_port=1234,
            remote_ip="8.8.8.8",
            protocol="tcp"
        )
        assert conn.remote_port is None

    def test_invalid_local_port(self):
        """Invalid local port should raise ValidationError."""
        with pytest.raises(ValidationError):
            ConnectionBase(
                local_ip="192.168.1.1",
                local_port=70000,
                remote_ip="8.8.8.8",
                protocol="tcp"
            )


class TestConnectionBaseProtocol:
    """Test protocol validation for ConnectionBase."""

    def test_valid_connection_protocols(self):
        """Valid protocols should be accepted."""
        for protocol in ["tcp", "udp", "sctp", "ip"]:
            conn = ConnectionBase(
                local_ip="192.168.1.1",
                local_port=1234,
                remote_ip="8.8.8.8",
                protocol=protocol
            )
            assert conn.protocol == protocol

    def test_protocol_case_normalized(self):
        """Protocol in uppercase should be normalized to lowercase."""
        conn = ConnectionBase(
            local_ip="192.168.1.1",
            local_port=1234,
            remote_ip="8.8.8.8",
            protocol="TCP"
        )
        assert conn.protocol == "tcp"


# ============================================================================
# ARPEntryBase Tests
# ============================================================================

class TestARPEntryBaseIPAndMAC:
    """Test IP and MAC address validation for ARPEntryBase."""

    def test_valid_arp_entry(self):
        """Valid ARP entry with IPv4 and MAC should be accepted."""
        arp = ARPEntryBase(ip_address="192.168.1.1", mac_address="00:1A:2B:3C:4D:5E")
        assert arp.ip_address == "192.168.1.1"
        assert arp.mac_address == "00:1A:2B:3C:4D:5E"

    def test_valid_arp_entry_ipv6(self):
        """Valid ARP entry with IPv6 and MAC should be accepted."""
        arp = ARPEntryBase(ip_address="2001:db8::1", mac_address="00:1A:2B:3C:4D:5E")
        assert arp.ip_address == "2001:db8::1"
        assert arp.mac_address == "00:1A:2B:3C:4D:5E"

    def test_invalid_arp_ip(self):
        """Invalid IP in ARP entry should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ARPEntryBase(ip_address="invalid.ip", mac_address="00:1A:2B:3C:4D:5E")
        assert "Invalid IP address" in str(exc_info.value)

    def test_invalid_arp_mac(self):
        """Invalid MAC in ARP entry should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ARPEntryBase(ip_address="192.168.1.1", mac_address="invalid:mac")
        assert "Invalid MAC address" in str(exc_info.value)

    def test_unspecified_arp_ip_rejected(self):
        """Unspecified IP in ARP entry should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ARPEntryBase(ip_address="0.0.0.0", mac_address="00:1A:2B:3C:4D:5E")
        assert "Unspecified" in str(exc_info.value)


# ============================================================================
# RawImportBase Tests
# ============================================================================

class TestRawImportBaseSourceType:
    """Test source_type validation for RawImportBase."""

    def test_valid_source_types(self):
        """All valid source types should be accepted."""
        valid_sources = ["nmap", "arp", "netstat", "ping", "traceroute", "pcap", "manual"]
        for source in valid_sources:
            raw = RawImportBase(
                source_type=source,
                import_type="xml",
                raw_data="test data"
            )
            assert raw.source_type == source

    def test_source_type_case_normalized(self):
        """Source type in uppercase should be normalized to lowercase."""
        raw = RawImportBase(
            source_type="NMAP",
            import_type="xml",
            raw_data="test data"
        )
        assert raw.source_type == "nmap"

    def test_invalid_source_type(self):
        """Invalid source type should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RawImportBase(
                source_type="invalid_source",
                import_type="xml",
                raw_data="test data"
            )
        assert "Invalid source type" in str(exc_info.value)


class TestRawImportBaseImportType:
    """Test import_type validation for RawImportBase."""

    def test_valid_import_types(self):
        """All valid import types should be accepted."""
        valid_imports = ["xml", "grep", "json", "text", "csv", "pcap", "raw"]
        for import_type in valid_imports:
            raw = RawImportBase(
                source_type="nmap",
                import_type=import_type,
                raw_data="test data"
            )
            assert raw.import_type == import_type

    def test_import_type_case_normalized(self):
        """Import type in uppercase should be normalized to lowercase."""
        raw = RawImportBase(
            source_type="nmap",
            import_type="XML",
            raw_data="test data"
        )
        assert raw.import_type == "xml"

    def test_invalid_import_type(self):
        """Invalid import type should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RawImportBase(
                source_type="nmap",
                import_type="invalid_type",
                raw_data="test data"
            )
        assert "Invalid import type" in str(exc_info.value)


class TestRawImportBaseRawData:
    """Test raw_data validation for RawImportBase."""

    def test_valid_raw_data(self):
        """Valid raw data should be accepted."""
        raw = RawImportBase(
            source_type="nmap",
            import_type="xml",
            raw_data="<test>data</test>"
        )
        assert raw.raw_data == "<test>data</test>"

    def test_large_valid_raw_data(self):
        """Large but valid raw data should be accepted."""
        large_data = "a" * (1024 * 1024)  # 1 MB
        raw = RawImportBase(
            source_type="nmap",
            import_type="text",
            raw_data=large_data
        )
        assert len(raw.raw_data) == 1024 * 1024

    def test_empty_raw_data(self):
        """Empty raw data should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RawImportBase(
                source_type="nmap",
                import_type="xml",
                raw_data=""
            )
        assert "empty" in str(exc_info.value).lower()

    def test_whitespace_only_raw_data(self):
        """Whitespace-only raw data should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RawImportBase(
                source_type="nmap",
                import_type="xml",
                raw_data="   "
            )
        assert "empty" in str(exc_info.value).lower()

    def test_raw_data_exceeds_max_size(self):
        """Raw data exceeding 10 MB should raise ValidationError."""
        large_data = "a" * (11 * 1024 * 1024)  # 11 MB
        with pytest.raises(ValidationError) as exc_info:
            RawImportBase(
                source_type="nmap",
                import_type="text",
                raw_data=large_data
            )
        assert "too large" in str(exc_info.value).lower()


class TestRawImportBaseSourceHost:
    """Test source_host validation for RawImportBase."""

    def test_valid_source_host_ipv4(self):
        """Valid IPv4 as source host should be accepted."""
        raw = RawImportBase(
            source_type="nmap",
            import_type="xml",
            raw_data="test data",
            source_host="192.168.1.1"
        )
        assert raw.source_host == "192.168.1.1"

    def test_valid_source_host_ipv6(self):
        """Valid IPv6 as source host should be accepted."""
        raw = RawImportBase(
            source_type="nmap",
            import_type="xml",
            raw_data="test data",
            source_host="2001:db8::1"
        )
        assert raw.source_host == "2001:db8::1"

    def test_valid_source_host_hostname(self):
        """Valid hostname as source host should be accepted."""
        raw = RawImportBase(
            source_type="nmap",
            import_type="xml",
            raw_data="test data",
            source_host="scanner.example.com"
        )
        assert raw.source_host == "scanner.example.com"

    def test_source_host_optional(self):
        """Source host should be optional (None)."""
        raw = RawImportBase(
            source_type="nmap",
            import_type="xml",
            raw_data="test data",
            source_host=None
        )
        assert raw.source_host is None

    def test_invalid_source_host(self):
        """Invalid source host should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            RawImportBase(
                source_type="nmap",
                import_type="xml",
                raw_data="test data",
                source_host="invalid host!"
            )
        assert "Invalid source host" in str(exc_info.value)


# ============================================================================
# DeviceIdentityBase Tests
# ============================================================================

class TestDeviceIdentityBaseDeviceType:
    """Test device_type validation for DeviceIdentityBase."""

    def test_valid_device_type(self):
        """Valid device type should be accepted."""
        device = DeviceIdentityBase(device_type="router")
        assert device.device_type == "router"

    def test_device_type_case_normalized(self):
        """Device type in uppercase should be normalized to lowercase."""
        device = DeviceIdentityBase(device_type="FIREWALL")
        assert device.device_type == "firewall"

    def test_device_type_optional(self):
        """Device type should be optional (None)."""
        device = DeviceIdentityBase(device_type=None)
        assert device.device_type is None

    def test_invalid_device_type(self):
        """Invalid device type should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DeviceIdentityBase(device_type="invalid")
        assert "Invalid device type" in str(exc_info.value)


class TestDeviceIdentityBaseMACAddressesList:
    """Test mac_addresses list validation for DeviceIdentityBase."""

    def test_valid_mac_list(self):
        """Valid MAC address list should be accepted."""
        device = DeviceIdentityBase(
            mac_addresses=["00:1A:2B:3C:4D:5E", "AA:BB:CC:DD:EE:FF"]
        )
        assert len(device.mac_addresses) == 2
        assert device.mac_addresses[0] == "00:1A:2B:3C:4D:5E"

    def test_mac_list_single_entry(self):
        """Single-entry MAC list should be accepted."""
        device = DeviceIdentityBase(mac_addresses=["00:1A:2B:3C:4D:5E"])
        assert len(device.mac_addresses) == 1

    def test_mac_list_empty(self):
        """Empty MAC list should be accepted."""
        device = DeviceIdentityBase(mac_addresses=[])
        assert device.mac_addresses == []

    def test_mac_list_optional(self):
        """MAC addresses list should be optional (None)."""
        device = DeviceIdentityBase(mac_addresses=None)
        assert device.mac_addresses is None

    def test_invalid_mac_in_list(self):
        """Invalid MAC in list should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DeviceIdentityBase(
                mac_addresses=["00:1A:2B:3C:4D:5E", "invalid:mac"]
            )
        assert "Invalid MAC address" in str(exc_info.value)


class TestDeviceIdentityBaseIPAddressesList:
    """Test ip_addresses list validation for DeviceIdentityBase."""

    def test_valid_ip_list(self):
        """Valid IP address list should be accepted."""
        device = DeviceIdentityBase(
            ip_addresses=["192.168.1.1", "192.168.1.2"]
        )
        assert len(device.ip_addresses) == 2
        assert device.ip_addresses[0] == "192.168.1.1"

    def test_valid_ip_list_mixed(self):
        """Mixed IPv4 and IPv6 list should be accepted."""
        device = DeviceIdentityBase(
            ip_addresses=["192.168.1.1", "2001:db8::1"]
        )
        assert len(device.ip_addresses) == 2

    def test_ip_list_single_entry(self):
        """Single-entry IP list should be accepted."""
        device = DeviceIdentityBase(ip_addresses=["192.168.1.1"])
        assert len(device.ip_addresses) == 1

    def test_ip_list_empty(self):
        """Empty IP list should be accepted."""
        device = DeviceIdentityBase(ip_addresses=[])
        assert device.ip_addresses == []

    def test_ip_list_optional(self):
        """IP addresses list should be optional (None)."""
        device = DeviceIdentityBase(ip_addresses=None)
        assert device.ip_addresses is None

    def test_invalid_ip_in_list(self):
        """Invalid IP in list should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DeviceIdentityBase(
                ip_addresses=["192.168.1.1", "invalid.ip"]
            )
        assert "Invalid IP address" in str(exc_info.value)


class TestDeviceIdentityBaseIntegration:
    """Integration tests for DeviceIdentityBase."""

    def test_device_with_all_fields(self):
        """Device identity with all fields should be accepted."""
        device = DeviceIdentityBase(
            name="router01",
            device_type="router",
            mac_addresses=["00:1A:2B:3C:4D:5E"],
            ip_addresses=["192.168.1.1"],
            notes="Main office router"
        )
        assert device.name == "router01"
        assert device.device_type == "router"
        assert len(device.mac_addresses) == 1
        assert len(device.ip_addresses) == 1
        assert device.notes == "Main office router"


# ============================================================================
# DeviceIdentityUpdate Tests
# ============================================================================

class TestDeviceIdentityUpdateAllFieldsOptional:
    """Test that all fields in DeviceIdentityUpdate are optional."""

    def test_empty_device_identity_update(self):
        """Creating DeviceIdentityUpdate with no fields should succeed."""
        update = DeviceIdentityUpdate()
        assert update.device_type is None
        assert update.mac_addresses is None
        assert update.ip_addresses is None

    def test_device_identity_update_single_field(self):
        """DeviceIdentityUpdate with single field should work."""
        update = DeviceIdentityUpdate(device_type="router")
        assert update.device_type == "router"
        assert update.mac_addresses is None

    def test_device_identity_update_validates_device_type(self):
        """DeviceIdentityUpdate should validate device type."""
        with pytest.raises(ValidationError) as exc_info:
            DeviceIdentityUpdate(device_type="invalid")
        assert "Invalid device type" in str(exc_info.value)

    def test_device_identity_update_validates_mac_list(self):
        """DeviceIdentityUpdate should validate MAC addresses."""
        with pytest.raises(ValidationError) as exc_info:
            DeviceIdentityUpdate(mac_addresses=["invalid:mac"])
        assert "Invalid MAC address" in str(exc_info.value)

    def test_device_identity_update_validates_ip_list(self):
        """DeviceIdentityUpdate should validate IP addresses."""
        with pytest.raises(ValidationError) as exc_info:
            DeviceIdentityUpdate(ip_addresses=["invalid.ip"])
        assert "Invalid IP address" in str(exc_info.value)


# ============================================================================
# Integration and Complex Scenarios
# ============================================================================

class TestComplexScenarios:
    """Test complex scenarios with multiple validators."""

    def test_host_with_all_optional_fields(self):
        """Host with all optional fields set should work."""
        host = HostBase(
            ip_address="192.168.1.1",
            mac_address="00:1A:2B:3C:4D:5E",
            hostname="server",
            fqdn="server.example.com",
            device_type="server",
            os_family="linux",
            criticality="high",
            os_confidence=95,
            notes="Production database server"
        )
        assert host.ip_address == "192.168.1.1"
        assert host.device_type == "server"
        assert host.os_confidence == 95

    def test_port_with_optional_fields(self):
        """Port with optional service info should work."""
        port = PortBase(
            port_number=443,
            protocol="tcp",
            state="open",
            service_name="https",
            service_version="nginx/1.25.0"
        )
        assert port.port_number == 443
        assert port.service_name == "https"

    def test_connection_with_optional_remote_port(self):
        """Connection without remote port should work."""
        conn = ConnectionBase(
            local_ip="192.168.1.100",
            local_port=54321,
            remote_ip="8.8.8.8",
            protocol="udp"
        )
        assert conn.remote_port is None

    def test_raw_import_with_max_size_data(self):
        """Raw import with data at 10MB limit should work."""
        max_data = "x" * (10 * 1024 * 1024)
        raw = RawImportBase(
            source_type="pcap",
            import_type="pcap",
            raw_data=max_data
        )
        assert len(raw.raw_data) == 10 * 1024 * 1024

"""Test script for Netstat and ARP parsers."""

from pathlib import Path

from parsers.netstat import NetstatParser
from parsers.arp import ArpParser

REPO_ROOT = Path(__file__).resolve().parents[1]
NETSTAT_LINUX_SAMPLE = (REPO_ROOT / "samples" / "netstat_linux.txt").read_text()


def test_netstat_linux():
    """Test Linux netstat parser."""
    print("\n=== Testing Netstat - Linux Format ===")
    data = NETSTAT_LINUX_SAMPLE

    parser = NetstatParser()
    result = parser.parse(data)

    print(f"Success: {result.success}")
    print(f"Connections parsed: {len(result.connections)}")
    for conn in result.connections:
        print(
            f"  {conn.protocol.upper()} {conn.local_ip}:{conn.local_port} -> {conn.remote_ip}:{conn.remote_port} [{conn.state}] PID={conn.pid} ({conn.process_name})"
        )

    assert result.success, "Linux netstat parse failed"
    assert len(result.connections) == 4, f"Expected 4 connections, got {len(result.connections)}"
    assert result.connections[0].pid == 1234, "PID parsing failed"
    assert result.connections[0].process_name == "sshd", "Process name parsing failed"
    print("✓ Linux netstat test passed")


def test_netstat_macos():
    """Test macOS netstat parser."""
    print("\n=== Testing Netstat - macOS Format ===")
    data = """Active Internet connections (including servers)
Proto Recv-Q Send-Q  Local Address          Foreign Address        (state)
tcp4       0      0  *.22                   *.*                    LISTEN
tcp4       0      0  192.168.1.10.443       10.0.0.5.54321         ESTABLISHED
tcp6       0      0  *.80                   *.*                    LISTEN
udp4       0      0  *.68                   *.*                    """

    parser = NetstatParser()
    result = parser.parse(data)

    print(f"Success: {result.success}")
    print(f"Connections parsed: {len(result.connections)}")
    for conn in result.connections:
        print(
            f"  {conn.protocol.upper()} {conn.local_ip}:{conn.local_port} -> {conn.remote_ip}:{conn.remote_port} [{conn.state}]"
        )

    assert result.success, "macOS netstat parse failed"
    assert len(result.connections) == 4, f"Expected 4 connections, got {len(result.connections)}"
    assert result.connections[1].local_ip == "192.168.1.10", "Address parsing failed"
    assert result.connections[1].local_port == 443, "Port parsing failed"
    print("✓ macOS netstat test passed")


def test_netstat_windows():
    """Test Windows netstat parser."""
    print("\n=== Testing Netstat - Windows Format ===")
    data = """Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:22             0.0.0.0:0              LISTENING       1234
  TCP    192.168.1.10:443       10.0.0.5:54321         ESTABLISHED     5678
  TCP    [::]:80                [::]:0                 LISTENING       9012
  UDP    0.0.0.0:68             *:*                                    2345"""

    parser = NetstatParser()
    result = parser.parse(data)

    print(f"Success: {result.success}")
    print(f"Connections parsed: {len(result.connections)}")
    for conn in result.connections:
        print(
            f"  {conn.protocol.upper()} {conn.local_ip}:{conn.local_port} -> {conn.remote_ip}:{conn.remote_port} [{conn.state}] PID={conn.pid}"
        )

    assert result.success, "Windows netstat parse failed"
    assert len(result.connections) == 4, f"Expected 4 connections, got {len(result.connections)}"
    assert result.connections[2].local_ip == "::", "IPv6 parsing failed"
    assert result.connections[0].pid == 1234, "PID parsing failed"
    print("✓ Windows netstat test passed")


def test_arp_linux():
    """Test Linux ARP parser."""
    print("\n=== Testing ARP - Linux Format ===")
    data = """router (192.168.1.1) at 00:11:22:33:44:55 [ether] on eth0
server (192.168.1.10) at aa:bb:cc:dd:ee:ff [ether] on eth0
? (192.168.1.20) at <incomplete> on eth0"""

    parser = ArpParser()
    result = parser.parse(data)

    print(f"Success: {result.success}")
    print(f"ARP entries parsed: {len(result.arp_entries)}")
    for entry in result.arp_entries:
        print(
            f"  {entry.ip_address} -> {entry.mac_address} on {entry.interface} ({entry.entry_type})"
        )

    assert result.success, "Linux ARP parse failed"
    assert len(result.arp_entries) == 3, f"Expected 3 ARP entries, got {len(result.arp_entries)}"
    assert result.arp_entries[0].mac_address == "00:11:22:33:44:55", "MAC address parsing failed"
    assert result.arp_entries[2].mac_address is None, "Incomplete entry should have None MAC"
    print("✓ Linux ARP test passed")


def test_arp_linux_ip_neigh():
    """Test Linux ip neigh format ARP parser."""
    print("\n=== Testing ARP - Linux ip neigh Format ===")
    data = """192.168.1.1 dev eth0 lladdr 00:11:22:33:44:55 REACHABLE
192.168.1.10 dev eth0 lladdr aa:bb:cc:dd:ee:ff STALE
192.168.1.20 dev eth0  FAILED"""

    parser = ArpParser()
    result = parser.parse(data)

    print(f"Success: {result.success}")
    print(f"ARP entries parsed: {len(result.arp_entries)}")
    for entry in result.arp_entries:
        print(
            f"  {entry.ip_address} -> {entry.mac_address} on {entry.interface} ({entry.entry_type})"
        )

    assert result.success, "Linux ip neigh parse failed"
    assert len(result.arp_entries) == 3, f"Expected 3 ARP entries, got {len(result.arp_entries)}"
    assert result.arp_entries[2].mac_address is None, "FAILED entry should have None MAC"
    assert result.arp_entries[2].entry_type == "failed", "Entry type should be 'failed'"
    print("✓ Linux ip neigh ARP test passed")


def test_arp_macos():
    """Test macOS ARP parser."""
    print("\n=== Testing ARP - macOS Format ===")
    data = """? (192.168.1.1) at 0:11:22:33:44:55 on en0 ifscope [ethernet]
? (192.168.1.10) at aa:bb:cc:dd:ee:ff on en0 ifscope [ethernet]
? (192.168.1.20) at (incomplete) on en0 ifscope [ethernet]"""

    parser = ArpParser()
    result = parser.parse(data)

    print(f"Success: {result.success}")
    print(f"ARP entries parsed: {len(result.arp_entries)}")
    for entry in result.arp_entries:
        print(
            f"  {entry.ip_address} -> {entry.mac_address} on {entry.interface} ({entry.entry_type})"
        )

    assert result.success, "macOS ARP parse failed"
    assert len(result.arp_entries) == 3, f"Expected 3 ARP entries, got {len(result.arp_entries)}"
    # Note: macOS uses single-digit hex without leading zeros
    assert result.arp_entries[0].mac_address == "00:11:22:33:44:55", "MAC normalization failed"
    assert result.arp_entries[2].mac_address is None, "Incomplete entry should have None MAC"
    print("✓ macOS ARP test passed")


def test_arp_windows():
    """Test Windows ARP parser."""
    print("\n=== Testing ARP - Windows Format ===")
    data = """Interface: 192.168.1.100 --- 0x4
  Internet Address      Physical Address      Type
  192.168.1.1           00-11-22-33-44-55     dynamic
  192.168.1.10          aa-bb-cc-dd-ee-ff     dynamic
  192.168.1.255         ff-ff-ff-ff-ff-ff     static"""

    parser = ArpParser()
    result = parser.parse(data)

    print(f"Success: {result.success}")
    print(f"ARP entries parsed: {len(result.arp_entries)}")
    for entry in result.arp_entries:
        print(
            f"  {entry.ip_address} -> {entry.mac_address} on {entry.interface} ({entry.entry_type})"
        )

    assert result.success, "Windows ARP parse failed"
    assert len(result.arp_entries) == 3, f"Expected 3 ARP entries, got {len(result.arp_entries)}"
    assert result.arp_entries[0].mac_address == "00:11:22:33:44:55", "MAC normalization failed"
    assert result.arp_entries[2].entry_type == "static", "Entry type should be 'static'"
    assert result.arp_entries[0].interface == "192.168.1.100", "Interface should be set"
    print("✓ Windows ARP test passed")


def test_format_detection():
    """Test automatic format detection."""
    print("\n=== Testing Format Auto-Detection ===")

    netstat_parser = NetstatParser()
    arp_parser = ArpParser()

    # Test netstat format detection
    linux_netstat = "Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name\ntcp        0      0 0.0.0.0:22              0.0.0.0:*               LISTEN      1234/sshd"
    assert netstat_parser.detect_format(linux_netstat) == "linux", "Failed to detect Linux netstat"
    print("✓ Linux netstat detection passed")

    macos_netstat = "Proto Recv-Q Send-Q  Local Address          Foreign Address        (state)\ntcp4       0      0  *.22                   *.*                    LISTEN"
    assert netstat_parser.detect_format(macos_netstat) == "macos", "Failed to detect macOS netstat"
    print("✓ macOS netstat detection passed")

    windows_netstat = "Proto  Local Address          Foreign Address        State           PID\nTCP    0.0.0.0:22             0.0.0.0:0              LISTENING       1234"
    assert netstat_parser.detect_format(windows_netstat) == "windows", "Failed to detect Windows netstat"
    print("✓ Windows netstat detection passed")

    # Test ARP format detection
    linux_arp = "router (192.168.1.1) at 00:11:22:33:44:55 [ether] on eth0"
    assert arp_parser.detect_format(linux_arp) == "linux", "Failed to detect Linux ARP"
    print("✓ Linux ARP detection passed")

    macos_arp = "? (192.168.1.1) at 0:11:22:33:44:55 on en0 ifscope [ethernet]"
    assert arp_parser.detect_format(macos_arp) == "macos", "Failed to detect macOS ARP"
    print("✓ macOS ARP detection passed")

    windows_arp = "Interface: 192.168.1.100 --- 0x4\n  Internet Address      Physical Address      Type"
    assert arp_parser.detect_format(windows_arp) == "windows", "Failed to detect Windows ARP"
    print("✓ Windows ARP detection passed")


def test_edge_cases():
    """Test edge cases and special scenarios."""
    print("\n=== Testing Edge Cases ===")

    # Test netstat with explicit platform override
    parser = NetstatParser()
    data = "tcp        0      0 0.0.0.0:22              0.0.0.0:*               LISTEN      1234/sshd"
    result = parser.parse(data, platform="linux")
    assert result.success, "Explicit platform override failed"
    print("✓ Netstat platform override passed")

    # Test ARP MAC normalization
    arp_parser = ArpParser()
    data = """Interface: 192.168.1.100 --- 0x4
  Internet Address      Physical Address      Type
  192.168.1.1           0-1-2-3-4-5           dynamic"""

    result = arp_parser.parse(data)
    if result.arp_entries:
        mac = result.arp_entries[0].mac_address
        assert mac == "00:01:02:03:04:05", f"MAC normalization failed: got {mac}"
    print("✓ MAC normalization edge case passed")

    # Test empty input
    netstat_result = parser.parse("")
    assert not netstat_result.success, "Empty input should fail"
    assert len(netstat_result.errors) > 0, "Empty input should have errors"
    print("✓ Empty input handling passed")


if __name__ == "__main__":
    try:
        test_netstat_linux()
        test_netstat_macos()
        test_netstat_windows()
        test_arp_linux()
        test_arp_linux_ip_neigh()
        test_arp_macos()
        test_arp_windows()
        test_format_detection()
        test_edge_cases()

        print("\n" + "=" * 50)
        print("✓ ALL TESTS PASSED")
        print("=" * 50)
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

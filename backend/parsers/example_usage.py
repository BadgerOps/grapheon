"""Example usage of the network parsers."""

from parsers.nmap import NmapParser
from parsers import get_parser, PARSERS


def example_parse_nmap_xml():
    """Example: Parse NMAP XML output."""
    print("=" * 60)
    print("Example 1: Parse NMAP XML Output")
    print("=" * 60)

    xml_data = """<?xml version="1.0"?>
<nmaprun scanner="nmap" args="nmap -sV -O 192.168.1.0/24" start="1675296000">
<host><status state="up"/>
<address addr="192.168.1.1" addrtype="ipv4"/>
<address addr="00:11:22:33:44:55" addrtype="mac" vendor="Cisco Systems"/>
<hostnames><hostname name="router.local" type="PTR"/></hostnames>
<ports>
<port protocol="tcp" portid="22"><state state="open"/><service name="ssh" product="OpenSSH" version="8.9p1" conf="10"/></port>
<port protocol="tcp" portid="80"><state state="open"/><service name="http" product="nginx" version="1.18.0" conf="10"/></port>
<port protocol="tcp" portid="443"><state state="open"/><service name="https" product="nginx" version="1.18.0" extrainfo="(Debian)" conf="10"/></port>
<port protocol="tcp" portid="3306"><state state="filtered"/><service name="mysql" product="MySQL" version="5.7.22" conf="8"/></port>
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

    parser = NmapParser()
    result = parser.parse(xml_data, format_hint="xml")

    print(f"\nParsing Status: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Source Type: {result.source_type}")
    print(f"Hosts Found: {len(result.hosts)}")

    for host in result.hosts:
        print(f"\n  Host: {host.ip_address}")
        print(f"    Hostname: {host.hostname}")
        print(f"    MAC: {host.mac_address} ({host.vendor})")
        print(f"    OS: {host.os_name}")
        print(f"    OS Family: {host.os_family}")
        print(f"    OS Confidence: {host.os_confidence}%")
        print(f"    Ports ({len(host.ports)}):")

        for port in host.ports:
            service = ""
            if port.service_product:
                service = f"{port.service_product}"
                if port.service_version:
                    service += f" {port.service_version}"
            print(
                f"      {port.port_number:5d}/{port.protocol:3s} {port.state:8s} - {port.service_name:6s} {service}"
            )


def example_parse_nmap_grep():
    """Example: Parse NMAP greppable output."""
    print("\n" + "=" * 60)
    print("Example 2: Parse NMAP Greppable Output")
    print("=" * 60)

    grep_data = """# Nmap 7.92 scan initiated
Host: 192.168.1.1 (router.local)	Ports: 22/open/tcp//ssh/OpenSSH 8.9///,80/open/tcp//http/nginx 1.18///,443/open/tcp//https/nginx 1.18/(Debian)/,3306/filtered/tcp//mysql/MySQL 5.7.22//	OS: Linux 5.4 - 5.14	MAC: 00:11:22:33:44:55 (Cisco Systems)
Host: 192.168.1.100 (macbook.local)	Ports: 22/open/tcp//ssh/OpenSSH 7.9///,5900/filtered/tcp//vnc/RealVNC 6.7//	OS: Mac OS X 10.12 - 11.6	MAC: AA:BB:CC:DD:EE:FF (Apple)
Host: 192.168.1.50 (server.local)	Ports: 3306/open/tcp//mysql/MySQL 5.7.22///	OS: Linux	MAC: 11:22:33:44:55:66 (Dell)
# Nmap done"""

    parser = NmapParser()
    result = parser.parse(grep_data, format_hint="grep")

    print(f"\nParsing Status: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Hosts Found: {len(result.hosts)}")

    for host in result.hosts:
        open_ports = sum(1 for p in host.ports if p.state == "open")
        filtered_ports = sum(1 for p in host.ports if p.state == "filtered")

        print(f"\n  {host.ip_address:15s} - {host.hostname:20s}")
        print(f"    OS: {host.os_name} ({host.os_family})")
        print(f"    Ports: {open_ports} open, {filtered_ports} filtered")


def example_auto_format_detection():
    """Example: Auto-detect format."""
    print("\n" + "=" * 60)
    print("Example 3: Auto-detect Format")
    print("=" * 60)

    # Test data - XML
    xml_data = """<?xml version="1.0"?>
<nmaprun>
<host><status state="up"/>
<address addr="10.0.0.1" addrtype="ipv4"/>
<ports>
<port protocol="tcp" portid="22"><state state="open"/><service name="ssh"/></port>
</ports>
</host>
</nmaprun>"""

    # Test data - Grep
    grep_data = "Host: 10.0.0.2 (test.local)\tPorts: 22/open/tcp//ssh///"

    parser = NmapParser()

    print("\nDetecting XML format...")
    detected_format = parser.detect_format(xml_data)
    print(f"  Detected: {detected_format}")

    result = parser.parse(xml_data)  # No format hint
    print(f"  Parse result: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"  Hosts found: {len(result.hosts)}")

    print("\nDetecting grep format...")
    detected_format = parser.detect_format(grep_data)
    print(f"  Detected: {detected_format}")

    result = parser.parse(grep_data)  # No format hint
    print(f"  Parse result: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"  Hosts found: {len(result.hosts)}")


def example_parser_registry():
    """Example: Using parser registry."""
    print("\n" + "=" * 60)
    print("Example 4: Parser Registry")
    print("=" * 60)

    print(f"\nAvailable parsers: {list(PARSERS.keys())}")

    parser = get_parser("nmap")
    print(f"Retrieved parser: {type(parser).__name__}")
    print(f"Source type: {parser.source_type}")

    # Try to get unknown parser
    try:
        get_parser("unknown")
    except ValueError as e:
        print("\nExpected error when requesting unknown parser:")
        print(f"  {e}")


def example_error_handling():
    """Example: Error handling."""
    print("\n" + "=" * 60)
    print("Example 5: Error Handling")
    print("=" * 60)

    # Empty input
    print("\nTesting empty input...")
    parser = NmapParser()
    result = parser.parse("")
    print(f"  Success: {result.success}")
    print(f"  Errors: {result.errors}")

    # Malformed XML
    print("\nTesting malformed XML...")
    result = parser.parse("<?xml version=\"1.0\"?>\n<nmaprun>", format_hint="xml")
    print(f"  Success: {result.success}")
    print(f"  Errors: {result.errors}")

    # Valid XML but no hosts
    print("\nTesting XML with no hosts...")
    result = parser.parse("<?xml version=\"1.0\"?>\n<nmaprun></nmaprun>")
    print(f"  Success: {result.success}")
    print(f"  Warnings: {result.warnings}")


def example_os_family_detection():
    """Example: OS family detection."""
    print("\n" + "=" * 60)
    print("Example 6: OS Family Detection")
    print("=" * 60)

    parser = NmapParser()

    test_cases = [
        ("Linux 5.4", "linux"),
        ("Ubuntu 20.04 LTS", "linux"),
        ("Debian GNU/Linux 11", "linux"),
        ("CentOS 7.9", "linux"),
        ("Windows 10", "windows"),
        ("Windows Server 2019", "windows"),
        ("Mac OS X 10.15", "macos"),
        ("macOS 11.6", "macos"),
        ("Cisco IOS 15.2", "network"),
        ("Juniper JunOS", "network"),
        ("Unknown", "unknown"),
    ]

    print("\nOS Family Mappings:")
    for os_string, expected_family in test_cases:
        detected_family = parser._infer_os_family(os_string)
        match = "✓" if detected_family == expected_family else "✗"
        print(
            f"  {match} {os_string:30s} -> {detected_family:10s} (expected: {expected_family})"
        )


if __name__ == "__main__":
    example_parse_nmap_xml()
    example_parse_nmap_grep()
    example_auto_format_detection()
    example_parser_registry()
    example_error_handling()
    example_os_family_detection()

    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)

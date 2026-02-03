# Network Parsers

This package provides parsers for various network scanning and discovery tools, converting their output into a standardized data model.

## Architecture

### Base Classes

The parser infrastructure is built on several core data classes defined in `base.py`:

#### Data Models

- **ParsedHost**: Represents a network host with IP, MAC, hostname, OS info, and list of ports
- **ParsedPort**: Represents an open/closed/filtered port with service information
- **ParsedConnection**: Represents a network connection from netstat
- **ParsedArpEntry**: Represents an ARP table entry
- **ParsedRouteHop**: Represents a hop in a traceroute
- **ParseResult**: The result of a parsing operation, containing all parsed data and any errors/warnings

#### Base Parser Class

The `BaseParser` abstract base class defines the interface all parsers must implement:

```python
class BaseParser(ABC):
    source_type: str = "unknown"

    @abstractmethod
    def parse(self, data: str, **kwargs) -> ParseResult:
        """Parse input data and return structured result."""
        pass

    def detect_format(self, data: str) -> Optional[str]:
        """Detect the format of input data."""
        return None

    def _infer_os_family(self, os_string: str) -> str:
        """Infer OS family from OS string."""
        # Maps to: linux, windows, macos, network, unknown
```

## Supported Parsers

### NMAP Parser

The `NmapParser` class handles NMAP scan output in two formats:

#### XML Format (`-oX`)

```bash
nmap -sV -O -oX output.xml 192.168.1.0/24
```

**Features:**
- Parses all host addresses (IPv4, IPv6, MAC)
- Extracts MAC vendor information
- Parses all ports with service information
- Extracts OS detection results with confidence scores
- Handles multiple hosts in a single scan
- Graceful error handling for malformed input

**Example:**
```python
from parsers.nmap import NmapParser

parser = NmapParser()
result = parser.parse(xml_data, format_hint="xml")

for host in result.hosts:
    print(f"{host.ip_address} - {host.hostname}")
    for port in host.ports:
        print(f"  {port.port_number}/{port.protocol} {port.state} ({port.service_name})")
```

#### Greppable Format (`-oG`)

```bash
nmap -sV -O -oG output.txt 192.168.1.0/24
```

**Features:**
- Parses Host lines with IP, hostname, and MAC
- Extracts port information in greppable format
- Parses OS identification
- Auto-detects format when not specified

**Example:**
```python
from parsers.nmap import NmapParser

parser = NmapParser()
result = parser.parse(grep_data, format_hint="grep")

for host in result.hosts:
    print(f"{host.ip_address}: {len(host.ports)} ports")
```

#### Format Auto-Detection

The parser automatically detects the input format:

```python
from parsers.nmap import NmapParser

parser = NmapParser()

# Will auto-detect XML or grep format
result = parser.parse(nmap_output)

if result.success:
    print(f"Found {len(result.hosts)} hosts")
else:
    print("Parsing failed:")
    for error in result.errors:
        print(f"  - {error}")
```

## Parser Registry

Access parsers through the centralized registry:

```python
from parsers import get_parser, PARSERS

# Get a specific parser
nmap_parser = get_parser("nmap")

# List all available parsers
print(list(PARSERS.keys()))  # ["nmap", ...]
```

## Error Handling

All parsers return a `ParseResult` object with:
- `success: bool` - Whether parsing succeeded
- `errors: List[str]` - List of error messages
- `warnings: List[str]` - List of warning messages
- `hosts: List[ParsedHost]` - Parsed hosts
- `connections: List[ParsedConnection]` - Parsed connections
- `arp_entries: List[ParsedArpEntry]` - Parsed ARP entries
- `route_hops: List[ParsedRouteHop]` - Parsed traceroute hops
- `parsed_at: datetime` - Timestamp of parsing

Example:
```python
result = parser.parse(data)

if not result.success:
    print("Errors:")
    for error in result.errors:
        print(f"  - {error}")

if result.warnings:
    print("Warnings:")
    for warning in result.warnings:
        print(f"  - {warning}")

print(f"Successfully parsed {len(result.hosts)} hosts")
```

## OS Family Classification

The parsers automatically classify operating systems into families:

- **linux**: Ubuntu, Debian, CentOS, RHEL, Fedora, Alpine, Arch
- **windows**: Microsoft Windows, Windows Server
- **macos**: Mac OS X, macOS, Darwin, OSX
- **network**: Cisco IOS, Juniper JunOS, routers, switches, firewalls
- **unknown**: Anything else

This is done via the `_infer_os_family()` method which can be overridden in subclasses.

## Usage Examples

### Parse NMAP XML and Display Results

```python
from parsers.nmap import NmapParser

parser = NmapParser()
result = parser.parse(xml_content)

for host in result.hosts:
    print(f"\nHost: {host.ip_address}")
    print(f"  Hostname: {host.hostname}")
    print(f"  MAC: {host.mac_address} ({host.vendor})")
    print(f"  OS: {host.os_name} ({host.os_confidence}%)")
    print(f"  Ports:")

    for port in host.ports:
        service = f"{port.service_name} {port.service_version}".strip()
        print(f"    {port.port_number}/{port.protocol}: {port.state} - {service}")
```

### Auto-Detect and Parse Format

```python
from parsers import get_parser

parser = get_parser("nmap")
result = parser.parse(unknown_format_data)

if result.success:
    print(f"Parsed {len(result.hosts)} hosts")
else:
    print(f"Failed: {result.errors}")
```

### Integrate with Database Models

```python
from parsers.nmap import NmapParser
from models import Host, Port

parser = NmapParser()
result = parser.parse(nmap_xml)

for parsed_host in result.hosts:
    # Create database record
    db_host = Host(
        ip_address=parsed_host.ip_address,
        mac_address=parsed_host.mac_address,
        hostname=parsed_host.hostname,
        os_name=parsed_host.os_name,
        os_family=parsed_host.os_family,
        os_confidence=parsed_host.os_confidence,
        vendor=parsed_host.vendor,
    )

    # Add ports
    for parsed_port in parsed_host.ports:
        port = Port(
            port_number=parsed_port.port_number,
            protocol=parsed_port.protocol,
            state=parsed_port.state,
            service_name=parsed_port.service_name,
            service_version=parsed_port.service_version,
        )
        db_host.ports.append(port)

    db.session.add(db_host)
    db.session.commit()
```

## Adding New Parsers

To add a new parser (e.g., for netstat, ARP, traceroute):

1. Create a new file in this directory (e.g., `parsers/netstat.py`)
2. Subclass `BaseParser`:

```python
from .base import BaseParser, ParseResult, ParsedConnection

class NetstatParser(BaseParser):
    source_type: str = "netstat"

    def parse(self, data: str, **kwargs) -> ParseResult:
        result = ParseResult(success=True, source_type=self.source_type)
        # Implement parsing logic
        return result

    def detect_format(self, data: str) -> Optional[str]:
        # Return "netstat" if detected, None otherwise
        pass
```

3. Register in `__init__.py`:

```python
from .netstat import NetstatParser

PARSERS = {
    "nmap": NmapParser,
    "netstat": NetstatParser,
}
```

## Testing

Basic tests for the NMAP parser are included in `tests/test_nmap_parser.py`. To run:

```bash
pytest tests/test_nmap_parser.py -v
```

Tests cover:
- Format detection (XML and grep)
- Successful parsing of valid input
- Error handling for malformed input
- OS family classification
- Edge cases (hosts without ports, IPv6, etc.)
- Auto-format detection

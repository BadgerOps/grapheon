# Parser Infrastructure - Getting Started

## Quick Start

### Installation

The parser infrastructure requires only Python's standard library. No additional dependencies needed!

```python
# Minimum Python version: 3.12+
# Required modules: abc, dataclasses, datetime, xml.etree.ElementTree, re
```

### Basic Usage

#### Parse NMAP XML

```python
from parsers.nmap import NmapParser

parser = NmapParser()
result = parser.parse(open('nmap_output.xml').read())

if result.success:
    for host in result.hosts:
        print(f"{host.ip_address} - {host.hostname} ({host.os_family})")
        for port in host.ports:
            print(f"  {port.port_number}/{port.protocol}: {port.state}")
else:
    print("Parsing failed:", result.errors)
```

#### Parse NMAP Greppable Format

```python
from parsers.nmap import NmapParser

parser = NmapParser()
result = parser.parse(open('nmap_output.txt').read())

for host in result.hosts:
    print(f"{host.ip_address}: {len(host.ports)} ports")
```

#### Use Parser Registry

```python
from parsers import get_parser

parser = get_parser("nmap")
result = parser.parse(nmap_data)
```

### Auto-Format Detection

The parser automatically detects the input format:

```python
from parsers.nmap import NmapParser

parser = NmapParser()

# Works with both XML and grep formats
result = parser.parse(unknown_data)

print(f"Parsed {len(result.hosts)} hosts")
```

## File Organization

```
parsers/
├── base.py              # Base classes and data models
├── nmap.py              # NMAP parser implementation
├── __init__.py          # Package initialization and registry
├── README.md            # Comprehensive documentation
├── example_usage.py     # Usage examples
└── GETTING_STARTED.md   # This file
```

## Key Classes

### ParsedHost

Represents a discovered network host:

```python
from parsers.base import ParsedHost

host = ParsedHost(
    ip_address="192.168.1.1",
    mac_address="AA:BB:CC:DD:EE:FF",
    hostname="router.local",
    os_name="Linux 5.4",
    os_family="linux",  # linux, windows, macos, network, unknown
    os_confidence=95,
    vendor="Cisco",
    ports=[...]  # List of ParsedPort objects
)
```

### ParsedPort

Represents a network port:

```python
from parsers.base import ParsedPort

port = ParsedPort(
    port_number=22,
    protocol="tcp",
    state="open",  # open, closed, filtered
    service_name="ssh",
    service_product="OpenSSH",
    service_version="8.9p1",
    confidence=10
)
```

### ParseResult

Contains the results of a parse operation:

```python
from parsers.base import ParseResult

result = ParseResult(
    success=True,
    source_type="nmap",
    hosts=[...],           # List of ParsedHost
    connections=[...],     # List of ParsedConnection
    arp_entries=[...],     # List of ParsedArpEntry
    route_hops=[...],      # List of ParsedRouteHop
    errors=[],            # List of error messages
    warnings=[],          # List of warning messages
    parsed_at=datetime.utcnow()
)
```

## Common Use Cases

### Extract All Open Ports

```python
from parsers.nmap import NmapParser

parser = NmapParser()
result = parser.parse(nmap_xml)

open_ports = []
for host in result.hosts:
    for port in host.ports:
        if port.state == "open":
            open_ports.append({
                "host": host.ip_address,
                "port": port.port_number,
                "service": port.service_name
            })

for item in open_ports:
    print(f"{item['host']}:{item['port']} ({item['service']})")
```

### Find All Services

```python
services = {}
for host in result.hosts:
    for port in host.ports:
        if port.service_name:
            key = f"{port.service_name}/{port.protocol}"
            if key not in services:
                services[key] = []
            services[key].append(f"{host.ip_address}:{port.port_number}")

for service, locations in sorted(services.items()):
    print(f"{service}: {len(locations)} instances")
    for loc in locations:
        print(f"  - {loc}")
```

### Filter by OS Family

```python
linux_hosts = [h for h in result.hosts if h.os_family == "linux"]
windows_hosts = [h for h in result.hosts if h.os_family == "windows"]
network_devices = [h for h in result.hosts if h.os_family == "network"]

print(f"Linux: {len(linux_hosts)}")
print(f"Windows: {len(windows_hosts)}")
print(f"Network: {len(network_devices)}")
```

### Count Services by Type

```python
from collections import Counter

service_counts = Counter()
for host in result.hosts:
    for port in host.ports:
        if port.service_name:
            service_counts[port.service_name] += 1

for service, count in service_counts.most_common(10):
    print(f"{service}: {count}")
```

## Error Handling

Always check the result status:

```python
from parsers.nmap import NmapParser

parser = NmapParser()
result = parser.parse(nmap_data)

if not result.success:
    print("Parsing failed with errors:")
    for error in result.errors:
        print(f"  - {error}")

if result.warnings:
    print("Warnings:")
    for warning in result.warnings:
        print(f"  - {warning}")
```

## NMAP Output Formats

### XML Format (-oX)

```bash
nmap -sV -O -oX output.xml 192.168.1.0/24
```

**Example**:
```xml
<?xml version="1.0"?>
<nmaprun scanner="nmap">
<host><status state="up"/>
<address addr="192.168.1.1" addrtype="ipv4"/>
<address addr="AA:BB:CC:DD:EE:FF" addrtype="mac" vendor="Vendor"/>
<ports>
<port protocol="tcp" portid="22"><state state="open"/>
<service name="ssh" product="OpenSSH" version="8.9"/></port>
</ports>
<os><osmatch name="Linux 5.4" accuracy="95"/></os>
</host>
</nmaprun>
```

### Greppable Format (-oG)

```bash
nmap -sV -O -oG output.txt 192.168.1.0/24
```

**Example**:
```
Host: 192.168.1.1 (router.local)	Ports: 22/open/tcp//ssh/OpenSSH 8.9///	OS: Linux 5.4	MAC: AA:BB:CC:DD:EE:FF (Vendor)
```

## Integration with Database

```python
from parsers.nmap import NmapParser
from models import Host, Port

parser = NmapParser()
result = parser.parse(nmap_xml)

for parsed_host in result.hosts:
    db_host = Host(
        ip_address=parsed_host.ip_address,
        mac_address=parsed_host.mac_address,
        hostname=parsed_host.hostname,
        os_name=parsed_host.os_name,
        os_family=parsed_host.os_family,
        os_confidence=parsed_host.os_confidence,
    )

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

## Creating a New Parser

To add a parser for a new tool:

1. Create `parsers/mytool.py`:

```python
from .base import BaseParser, ParseResult, ParsedHost

class MyToolParser(BaseParser):
    source_type: str = "mytool"

    def parse(self, data: str, **kwargs) -> ParseResult:
        result = ParseResult(success=True, source_type=self.source_type)

        # Implement your parsing logic
        # Create ParsedHost objects and add to result.hosts

        return result

    def detect_format(self, data: str) -> Optional[str]:
        # Return tool name if detected, None otherwise
        if "mytool" in data:
            return "mytool"
        return None
```

2. Register in `parsers/__init__.py`:

```python
from .mytool import MyToolParser

PARSERS = {
    "nmap": NmapParser,
    "mytool": MyToolParser,
}
```

## Performance Tips

1. **Use format hints** when you know the format:
   ```python
   result = parser.parse(data, format_hint="xml")
   ```

2. **Parse directly from file**:
   ```python
   with open("nmap_output.xml") as f:
       result = parser.parse(f.read())
   ```

3. **Check success before processing**:
   ```python
   if result.success:
       # Process result.hosts
   ```

## Testing

Run the test suite:

```bash
cd backend
python -m pytest tests/test_nmap_parser.py -v
```

## Troubleshooting

### "No module named parsers"

Make sure you're in the backend directory:
```bash
cd backend
python -c "from parsers.nmap import NmapParser"
```

### Parse failure with no clear error

Check the error messages:
```python
result = parser.parse(data)
if not result.success:
    for error in result.errors:
        print(error)
    for warning in result.warnings:
        print(warning)
```

### Format not detected

Explicitly specify the format:
```python
result = parser.parse(data, format_hint="xml")
# or
result = parser.parse(data, format_hint="grep")
```

## API Reference

### NmapParser.parse()

```python
def parse(self, data: str, format_hint: Optional[str] = None, **kwargs) -> ParseResult
```

**Parameters:**
- `data`: NMAP output string
- `format_hint`: "xml" or "grep" (optional, auto-detected if omitted)

**Returns:**
- `ParseResult` object containing parsed data

### NmapParser.detect_format()

```python
def detect_format(self, data: str) -> Optional[str]
```

**Parameters:**
- `data`: NMAP output string

**Returns:**
- "xml" if XML format detected
- "grep" if greppable format detected
- None if format not recognized

### get_parser()

```python
def get_parser(tool_name: str) -> BaseParser
```

**Parameters:**
- `tool_name`: Name of the tool ("nmap", etc.)

**Returns:**
- Parser instance

**Raises:**
- ValueError if tool_name not registered

## Resources

- Full documentation: `README.md`
- Implementation details: `PARSER_IMPLEMENTATION.md`
- Code examples: `example_usage.py`
- Test suite: `../tests/test_nmap_parser.py`

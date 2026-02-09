# Graphēon Imports Pipeline

Imports normalize raw network outputs into a consistent schema. Python 3.12 is required for parser execution.

## Import Flow

```mermaid
flowchart TD
    A[User] -->|paste text| B["POST /api/imports/raw"]
    A -->|upload file| C["POST /api/imports/file"]
    A -->|upload multiple| D["POST /api/imports/bulk"]

    B & C & D --> E[Import Router]
    E -->|source_type + data| F{Parser Registry<br/>backend/parsers/__init__.py}

    F -->|nmap| G[NmapParser<br/>XML or grep format]
    F -->|netstat| H[NetstatParser<br/>Linux/macOS/Windows]
    F -->|arp| I[ArpParser<br/>Linux/macOS/Windows]
    F -->|ping| J[PingParser<br/>standard/fping/iplist/nmap]
    F -->|traceroute| K[TracerouteParser<br/>Linux/Windows/MTR]
    F -->|pcap| L[PcapParser<br/>binary pcap or tcpdump text]

    G & H & I & J & K & L --> M[ParseResult]
    M --> N{Success?}
    N -->|yes| O[Upsert Pipeline]
    N -->|no| P[Mark import FAILED<br/>store error message]

    O --> Q[Create/update Host records]
    O --> R[Create Port records]
    O --> S[Create Connection records]
    O --> T[Create ARP entries]
    O --> U[Create RouteHop records]

    Q & R & S & T & U --> V[Tag Derivation<br/>IP / MAC / hostname /<br/>subnet / vendor / OS]
    V --> W[(SQLite Database)]
    W --> X[Record in raw_imports table<br/>status: completed]
```

## Entry Points

- `POST /api/imports/raw` accepts raw text payloads.
- `POST /api/imports/file` accepts file uploads.
- `POST /api/imports/bulk` accepts multiple files at once.

All import routes accept:

- `source_type`: `nmap`, `netstat`, `arp`, `ping`, `traceroute`, or `pcap`.
- `source_host`: IP or hostname of the collector. A host record is created or updated for this value.

## Parsing Flow

1. The import router selects a parser from `backend/parsers/` based on the `source_type` parameter.
2. Each parser auto-detects the input format (e.g., nmap XML vs grep output) via its `detect_format()` method.
3. The parser produces normalized objects: `ParsedHost`, `ParsedPort`, `ParsedConnection`, `ParsedARPEntry`, or `ParsedRouteHop`.
4. The pipeline upserts hosts, ports, connections, and ARP entries into the database.
5. Tags are derived from IPs, MACs, ports, services, and subnets (see `docs/tagging-correlation.md`).
6. The `raw_imports` table records the input, status, and any errors.

## Parser Output Models

```mermaid
classDiagram
    class ParseResult {
        +bool success
        +str source_type
        +list~ParsedHost~ hosts
        +list~ParsedPort~ ports
        +list~ParsedConnection~ connections
        +list~ParsedArpEntry~ arp_entries
        +list~ParsedRouteHop~ route_hops
        +list~str~ errors
        +list~str~ warnings
    }

    class ParsedHost {
        +str ip_address
        +str mac_address
        +str hostname
        +str fqdn
        +str vendor
        +str os_name
        +str os_family
        +str device_type
        +list~ParsedPort~ ports
    }

    class ParsedPort {
        +int port_number
        +str protocol
        +str state
        +str service_name
        +str product
        +str version
    }

    ParseResult --> ParsedHost
    ParseResult --> ParsedPort
    ParsedHost --> ParsedPort
```

## GUID Behavior

Hosts created from imports and raw input receive a GUID that is used as the stable entity identifier. IP or hostname changes do not replace the GUID.

## Errors

If no parser is available or parsing fails, the import record is marked failed and the error message is returned by `/api/imports/{id}`.

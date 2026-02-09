# Graphēon Tagging and Correlation

Tags capture normalized identifiers so data from different sources can be linked. Correlation uses tags plus MAC and IP logic to merge hosts. Python 3.12 is required for the tagging utilities.

## Tag Derivation

Tag builders live in `backend/utils/tagging.py`.

```mermaid
flowchart LR
    subgraph "Input Records"
        HOST[Host]
        PORT[Port]
        CONN[Connection]
        ARP[ARP Entry]
    end

    subgraph "Tag Builders"
        BH[build_host_tags]
        BP[build_port_tags]
        BC[build_connection_tags]
        BA[build_arp_tags]
    end

    HOST --> BH
    PORT --> BP
    CONN --> BC
    ARP --> BA

    subgraph "Generated Tags"
        HT["ip:10.0.0.1<br/>subnet:10.0.0.0/24<br/>mac:aa:bb:cc:dd:ee:ff<br/>hostname:web01<br/>fqdn:web01.corp.local<br/>vendor:Dell<br/>os_family:linux"]
        PT["port:80<br/>port_proto:80/tcp<br/>protocol:tcp<br/>state:open<br/>service:http<br/>product:nginx"]
        CT["local_ip:10.0.0.1<br/>remote_ip:10.0.0.2<br/>local_port:8080<br/>protocol:tcp<br/>state:ESTABLISHED<br/>process:python"]
        AT["ip:10.0.0.1<br/>mac:aa:bb:cc:dd:ee:ff<br/>interface:eth0<br/>entry_type:dynamic<br/>vendor:Dell"]
    end

    BH --> HT
    BP --> PT
    BC --> CT
    BA --> AT
```

- Host tags include `ip`, `subnet`, `mac`, `hostname`, `fqdn`, `vendor`, `os_family`, and `os`.
- Port tags include `port`, `port_proto`, `protocol`, `state`, `service`, `product`, and `version`.
- Connection tags include local and remote IPs, ports, subnets, protocol, state, and process.
- ARP tags include `ip`, `subnet`, `mac`, `interface`, `entry_type`, and `vendor`.

## Correlation

Correlation runs in `backend/services/correlation.py` and is triggered by `POST /api/correlate`. It runs in three phases:

```mermaid
flowchart TD
    START["POST /api/correlate"] --> P1

    subgraph "Phase 1: IP Consolidation"
        P1[Group hosts by IP address]
        P1 --> P1A{Multiple hosts<br/>share same IP?}
        P1A -->|yes| P1B[Merge into single host<br/>move ports/connections/tags]
        P1A -->|no| P1C[No action]
    end

    P1B & P1C --> P2

    subgraph "Phase 2: MAC-Based Device Identity"
        P2[Group hosts by MAC address]
        P2 --> P2A{Same MAC across<br/>different IPs?}
        P2A -->|yes| P2B[Create DeviceIdentity<br/>link multi-homed hosts]
        P2A -->|no| P2C[No action]
        P2B --> P2D{Same MAC AND<br/>same IP?}
        P2D -->|yes| P2E[Merge true duplicates]
        P2D -->|no| P2F[Keep separate<br/>linked by device_id]
    end

    P2E & P2F & P2C --> P3

    subgraph "Phase 3: Tag-Based Merging"
        P3[Group hosts by hostname/fqdn tags]
        P3 --> P3A{Ambiguous hostname?<br/>localhost, etc.}
        P3A -->|yes| P3B[Skip merge]
        P3A -->|no| P3C{Both hosts<br/>have MACs?}
        P3C -->|yes| P3D{MACs match?}
        P3C -->|no| P3E[Merge hosts]
        P3D -->|yes| P3E
        P3D -->|no| P3F[Record Conflict<br/>MAC mismatch]
    end

    P3E & P3B & P3F --> RESULT[CorrelationResult<br/>hosts_merged / conflicts_detected /<br/>device_identities_created]
```

- **Phase 1** merges hosts that share the same IP.
- **Phase 2** creates or updates `DeviceIdentity` links for same-MAC hosts across different IPs, and only merges true duplicate records (same MAC + same IP).
- **Phase 3** merges hosts that share high-confidence tags like hostname or FQDN.
- MAC conflicts prevent tag-based merges.
- Conflicts are recorded for MAC mismatches and hostname mismatches.

### High-confidence tag prefixes

Only `hostname:` and `fqdn:` tags trigger Phase 3 merges. Ambiguous hostnames (`localhost`, `localhost.localdomain`, `localhost.local`) are excluded from merge consideration.

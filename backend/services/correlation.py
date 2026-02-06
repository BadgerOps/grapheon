"""
Data correlation service for network hosts.

Handles:
- Host merging by IP and MAC address
- Conflict detection
- Data conflict resolution
- Unified host views
"""

import logging
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from models import Host, Port, Connection, ARPEntry, Conflict, DeviceIdentity
from utils.tagging import merge_tags

logger = logging.getLogger(__name__)

HIGH_CONFIDENCE_TAG_PREFIXES = ("hostname:", "fqdn:")
AMBIGUOUS_HOSTNAMES = {"localhost", "localhost.localdomain", "localhost.local"}


def _tag_value(tag: str) -> str:
    return tag.split(":", 1)[1] if ":" in tag else tag


def _is_ambiguous_hostname(value: str) -> bool:
    return value.lower() in AMBIGUOUS_HOSTNAMES


def _group_hosts_by_tags(hosts: List[Host]) -> Dict[str, List[Host]]:
    tag_groups: Dict[str, List[Host]] = {}
    for host in hosts:
        for tag in host.tags or []:
            if tag.startswith(HIGH_CONFIDENCE_TAG_PREFIXES):
                tag_groups.setdefault(tag, []).append(host)
    return tag_groups


def _should_merge_by_tag(primary: Host, secondary: Host, tag: str) -> bool:
    if not tag.startswith(HIGH_CONFIDENCE_TAG_PREFIXES):
        return False

    value = _tag_value(tag)
    if _is_ambiguous_hostname(value):
        return False

    # If both hosts have MACs and they differ, do not merge.
    if primary.mac_address and secondary.mac_address:
        if primary.mac_address.lower() != secondary.mac_address.lower():
            return False

    return True


@dataclass
class HostConflict:
    """Represents a data conflict in a host."""

    conflict_type: str  # mac_mismatch, os_mismatch, hostname_mismatch, etc
    host_id: int
    field: str  # which field has conflict
    values: List[Dict]  # [{"value": "...", "source": "...", "timestamp": "..."}]
    detected_at: datetime
    resolved: bool = False
    resolution: Optional[str] = None


@dataclass
class CorrelationResult:
    """Result of a correlation operation."""

    hosts_merged: int
    conflicts_detected: int
    conflicts_resolved: int
    hosts_updated: int
    device_identities_created: int
    timestamp: datetime


async def create_device_identity_from_mac(
    db: AsyncSession,
    mac_address: str,
    hosts: List[Host],
) -> DeviceIdentity:
    """
    Create a DeviceIdentity for hosts sharing the same MAC (multi-homed device).

    Instead of merging these hosts (which would lose per-subnet identity),
    we link them via device_id to indicate they're the same physical box.
    """
    # Check if a DeviceIdentity already exists for this MAC
    result = await db.execute(
        select(DeviceIdentity).where(
            DeviceIdentity.is_active.is_(True)
        )
    )
    existing_devices = result.scalars().all()
    for dev in existing_devices:
        if dev.mac_addresses and mac_address in dev.mac_addresses:
            # Already exists — update IP list and link new hosts
            existing_ips = set(dev.ip_addresses or [])
            for host in hosts:
                existing_ips.add(host.ip_address)
                host.device_id = dev.id
            dev.ip_addresses = sorted(existing_ips)
            dev.last_seen = datetime.utcnow()
            return dev

    # Infer device type from hosts
    device_types = set(h.device_type for h in hosts if h.device_type)
    inferred_type = device_types.pop() if len(device_types) == 1 else "router"

    # Collect all IPs
    ips = sorted(set(h.ip_address for h in hosts))

    # Build a useful name from hostname or IPs
    hostnames = [h.hostname for h in hosts if h.hostname]
    name = hostnames[0] if hostnames else f"Device ({mac_address})"

    device = DeviceIdentity(
        name=name,
        device_type=inferred_type,
        mac_addresses=[mac_address],
        ip_addresses=ips,
        source="mac_correlation",
        is_active=True,
    )
    db.add(device)
    await db.flush()  # Get the ID assigned

    # Link all hosts to this device identity
    for host in hosts:
        host.device_id = device.id

    logger.info(
        f"Created DeviceIdentity {device.id} for MAC {mac_address}: "
        f"{len(hosts)} hosts ({', '.join(ips)})"
    )

    return device


async def correlate_hosts(db: AsyncSession) -> CorrelationResult:
    """
    Run full correlation across all hosts.

    Process:
    1. Find hosts with matching IPs (merge by IP)
    2. Find hosts with matching MACs but different IPs (merge by MAC)
    3. Detect conflicts in OS, hostname, etc
    4. Update timestamps for active hosts

    Returns stats on merges performed and conflicts found.
    """
    logger.info("Starting host correlation")

    hosts_merged = 0
    conflicts_detected = 0
    conflicts_resolved = 0
    hosts_updated = 0
    device_identities_created = 0
    start_time = datetime.utcnow()

    # Get all active hosts
    result = await db.execute(select(Host).where(Host.is_active.is_(True)))
    hosts = result.scalars().all()

    logger.info(f"Processing {len(hosts)} active hosts")

    # Phase 1: Merge hosts with same IP (should not happen in normal operation)
    ip_groups = {}
    for host in hosts:
        if host.ip_address not in ip_groups:
            ip_groups[host.ip_address] = []
        ip_groups[host.ip_address].append(host)

    for ip, host_list in ip_groups.items():
        if len(host_list) > 1:
            logger.info(f"Found {len(host_list)} hosts with same IP {ip}")
            primary_host = host_list[0]
            for secondary_host in host_list[1:]:
                await merge_hosts(db, primary_host.id, secondary_host.id)
                hosts_merged += 1

    # Phase 2: Device Identity Detection + duplicate MAC merge
    # When same MAC appears on multiple hosts with DIFFERENT IPs,
    # create a DeviceIdentity to link them (non-destructive).
    # When same MAC has multiple hosts with SAME IP, merge (true duplicates).
    mac_groups = {}
    for host in hosts:
        if host.mac_address and host.is_active:
            mac_key = host.mac_address.lower()
            if mac_key not in mac_groups:
                mac_groups[mac_key] = []
            mac_groups[mac_key].append(host)

    for mac, host_list in mac_groups.items():
        if len(host_list) > 1:
            unique_ips = set(h.ip_address for h in host_list)
            if len(unique_ips) > 1:
                # Different IPs, same MAC = multi-homed device
                # Don't merge — create/update DeviceIdentity
                logger.info(
                    f"Multi-homed device detected: MAC {mac} has {len(unique_ips)} IPs: "
                    f"{', '.join(sorted(unique_ips))}"
                )
                await create_device_identity_from_mac(db, mac, host_list)
                device_identities_created += 1
            else:
                # Same IP and MAC = true duplicate host records — merge them
                primary_host = host_list[0]
                for secondary_host in host_list[1:]:
                    if secondary_host.is_active:
                        await merge_hosts(db, primary_host.id, secondary_host.id)
                        hosts_merged += 1

    # Phase 3: Merge hosts by high-confidence tags
    result = await db.execute(select(Host).where(Host.is_active.is_(True)))
    current_hosts = result.scalars().all()

    tag_groups = _group_hosts_by_tags(current_hosts)
    merged_ids: set[int] = set()

    for tag, host_list in tag_groups.items():
        active_hosts = [h for h in host_list if h.is_active and h.id not in merged_ids]
        if len(active_hosts) < 2:
            continue

        primary = active_hosts[0]
        for secondary in active_hosts[1:]:
            if secondary.id in merged_ids:
                continue
            if _should_merge_by_tag(primary, secondary, tag):
                await merge_hosts(db, primary.id, secondary.id, resolved_by="tag_merge")
                hosts_merged += 1
                merged_ids.add(secondary.id)

    # Phase 4: Detect conflicts
    result = await db.execute(select(Host).where(Host.is_active.is_(True)))
    current_hosts = result.scalars().all()

    for host in current_hosts:
        # Check for MAC address conflicts
        if host.mac_address:
            result = await db.execute(
                select(Conflict).where(
                    and_(
                        Conflict.host_id == host.id,
                        Conflict.conflict_type == "mac_mismatch",
                        Conflict.resolved.is_(False),
                    )
                )
            )
            existing_conflict = result.scalar_one_or_none()

            # Check ARP table for conflicting MACs
            arp_result = await db.execute(
                select(ARPEntry).where(ARPEntry.ip_address == host.ip_address)
            )
            arp_entries = arp_result.scalars().all()

            for arp_entry in arp_entries:
                if arp_entry.mac_address != host.mac_address:
                    if not existing_conflict:
                        conflict = Conflict(
                            host_id=host.id,
                            conflict_type="mac_mismatch",
                            field="mac_address",
                            values=[
                                {
                                    "value": host.mac_address,
                                    "source": "host_record",
                                    "timestamp": datetime.utcnow().isoformat(),
                                },
                                {
                                    "value": arp_entry.mac_address,
                                    "source": f"arp_table ({arp_entry.interface})",
                                    "timestamp": arp_entry.last_seen.isoformat(),
                                },
                            ],
                            detected_at=datetime.utcnow(),
                        )
                        db.add(conflict)
                        conflicts_detected += 1
                        logger.warning(
                            f"Detected MAC mismatch on host {host.id} ({host.ip_address}): "
                            f"{host.mac_address} vs {arp_entry.mac_address}"
                        )

        # Check for OS conflicts
        os_sources = {}
        if host.os_name and host.os_confidence:
            os_sources[f"{host.os_name} {host.os_version}"] = {
                "confidence": host.os_confidence,
                "source": "host_record",
                "timestamp": host.last_seen,
            }

        # Could add checks from ports, services, etc

        # Check for hostname conflicts
        hostnames = []
        if host.hostname:
            hostnames.append(host.hostname)
        if host.fqdn:
            hostnames.append(host.fqdn)
        if host.netbios_name:
            hostnames.append(host.netbios_name)

        if len(set(hostnames)) > 1:
            result = await db.execute(
                select(Conflict).where(
                    and_(
                        Conflict.host_id == host.id,
                        Conflict.conflict_type == "hostname_mismatch",
                        Conflict.resolved.is_(False),
                    )
                )
            )
            existing_conflict = result.scalar_one_or_none()

            if not existing_conflict:
                conflict = Conflict(
                    host_id=host.id,
                    conflict_type="hostname_mismatch",
                    field="hostname",
                    values=[
                        {"value": h, "source": "host_record", "timestamp": host.last_seen.isoformat()}
                        for h in set(hostnames)
                    ],
                    detected_at=datetime.utcnow(),
                )
                db.add(conflict)
                conflicts_detected += 1
                logger.warning(
                    f"Detected hostname mismatch on host {host.id} ({host.ip_address}): {hostnames}"
                )

    # Commit changes
    await db.commit()

    end_time = datetime.utcnow()
    result = CorrelationResult(
        hosts_merged=hosts_merged,
        conflicts_detected=conflicts_detected,
        conflicts_resolved=conflicts_resolved,
        hosts_updated=hosts_updated,
        device_identities_created=device_identities_created,
        timestamp=end_time,
    )

    logger.info(
        f"Correlation completed: {hosts_merged} merged, "
        f"{device_identities_created} device identities created, "
        f"{conflicts_detected} conflicts detected, "
        f"duration: {(end_time - start_time).total_seconds()}s"
    )

    return result


async def find_conflicts(db: AsyncSession, resolved: bool = False) -> List[Conflict]:
    """
    Find all unresolved data conflicts.

    Args:
        db: Database session
        resolved: Whether to find resolved or unresolved conflicts

    Returns:
        List of Conflict objects
    """
    result = await db.execute(select(Conflict).where(Conflict.resolved == resolved))
    return result.scalars().all()


async def merge_hosts(
    db: AsyncSession,
    primary_id: int,
    secondary_id: int,
    resolved_by: str = "auto_merge",
) -> Host:
    """
    Merge secondary host into primary, combining all data.

    Process:
    1. Reassign all ports from secondary to primary
    2. Reassign all connections from secondary to primary
    3. Merge source_types
    4. Keep highest confidence OS detection
    5. Preserve first_seen, update last_seen
    6. Soft-delete secondary host

    Args:
        db: Database session
        primary_id: ID of primary host (destination)
        secondary_id: ID of secondary host (source)
        resolved_by: Who/what triggered the merge

    Returns:
        Merged Host object
    """
    logger.info(f"Merging host {secondary_id} into {primary_id}")

    # Get both hosts
    primary_result = await db.execute(select(Host).where(Host.id == primary_id))
    primary = primary_result.scalar_one_or_none()

    secondary_result = await db.execute(select(Host).where(Host.id == secondary_id))
    secondary = secondary_result.scalar_one_or_none()

    if not primary or not secondary:
        raise ValueError("Primary or secondary host not found")

    # Merge source types
    primary_sources = primary.source_types or []
    secondary_sources = secondary.source_types or []
    merged_sources = list(set(primary_sources + secondary_sources))
    primary.source_types = merged_sources
    primary.tags = merge_tags(primary.tags, secondary.tags or [])

    # Keep highest confidence OS
    if secondary.os_confidence and (
        not primary.os_confidence or secondary.os_confidence > primary.os_confidence
    ):
        primary.os_name = secondary.os_name
        primary.os_version = secondary.os_version
        primary.os_family = secondary.os_family
        primary.os_confidence = secondary.os_confidence
        logger.info(
            f"Updated OS for host {primary_id}: "
            f"{secondary.os_name} {secondary.os_version} (confidence: {secondary.os_confidence})"
        )

    # Merge other fields (prefer non-null values from secondary)
    if secondary.hostname and not primary.hostname:
        primary.hostname = secondary.hostname
    if secondary.fqdn and not primary.fqdn:
        primary.fqdn = secondary.fqdn
    if secondary.netbios_name and not primary.netbios_name:
        primary.netbios_name = secondary.netbios_name
    if secondary.mac_address and not primary.mac_address:
        primary.mac_address = secondary.mac_address
    if secondary.device_type and not primary.device_type:
        primary.device_type = secondary.device_type
    if secondary.vendor and not primary.vendor:
        primary.vendor = secondary.vendor
    if secondary.owner and not primary.owner:
        primary.owner = secondary.owner
    if secondary.location and not primary.location:
        primary.location = secondary.location

    # Update timestamps
    if secondary.first_seen < primary.first_seen:
        primary.first_seen = secondary.first_seen
    primary.last_seen = datetime.utcnow()

    # Reassign ports from secondary to primary
    port_result = await db.execute(select(Port).where(Port.host_id == secondary_id))
    ports = port_result.scalars().all()
    for port in ports:
        port.host_id = primary_id
    logger.info(f"Reassigned {len(ports)} ports from secondary to primary")

    # Reassign connections from secondary to primary (local_ip)
    conn_result = await db.execute(
        select(Connection).where(Connection.local_ip == secondary.ip_address)
    )
    connections = conn_result.scalars().all()
    for conn in connections:
        conn.local_ip = primary.ip_address
    logger.info(f"Reassigned {len(connections)} connections to primary IP")

    # Mark secondary as inactive (soft delete)
    secondary.is_active = False
    secondary.last_seen = datetime.utcnow()

    # Create resolution record for any conflicts
    conflict_result = await db.execute(
        select(Conflict).where(Conflict.host_id == secondary_id)
    )
    conflicts = conflict_result.scalars().all()
    for conflict in conflicts:
        if not conflict.resolved:
            conflict.host_id = primary_id  # Move conflict to primary
            conflict.resolved = True
            conflict.resolved_by = resolved_by
            conflict.resolved_at = datetime.utcnow()
            conflict.resolution = f"Merged into host {primary_id}"

    await db.commit()
    await db.refresh(primary)

    logger.info(f"Successfully merged host {secondary_id} into {primary_id}")
    return primary


async def resolve_conflict(
    db: AsyncSession,
    conflict_id: int,
    resolution: str,
    resolved_by: str = "manual",
) -> Conflict:
    """
    Mark a conflict as resolved with a resolution description.

    Args:
        db: Database session
        conflict_id: ID of conflict to resolve
        resolution: How the conflict was resolved
        resolved_by: Who resolved it

    Returns:
        Updated Conflict object
    """
    result = await db.execute(select(Conflict).where(Conflict.id == conflict_id))
    conflict = result.scalar_one_or_none()

    if not conflict:
        raise ValueError(f"Conflict {conflict_id} not found")

    conflict.resolved = True
    conflict.resolution = resolution
    conflict.resolved_by = resolved_by
    conflict.resolved_at = datetime.utcnow()

    await db.commit()
    await db.refresh(conflict)

    logger.info(
        f"Resolved conflict {conflict_id} on host {conflict.host_id}: {resolution}"
    )
    return conflict


async def get_host_unified_view(db: AsyncSession, host_id: int) -> Dict:
    """
    Get a unified view of a host combining all source data.

    Returns comprehensive data including:
    - Host basic info
    - All ports
    - All connections
    - Related ARP entries
    - All conflicts
    - Data freshness metrics
    - Source types and coverage

    Args:
        db: Database session
        host_id: ID of host to view

    Returns:
        Dictionary with unified host view
    """
    # Get host
    host_result = await db.execute(select(Host).where(Host.id == host_id))
    host = host_result.scalar_one_or_none()

    if not host:
        raise ValueError(f"Host {host_id} not found")

    # Get ports
    port_result = await db.execute(select(Port).where(Port.host_id == host_id))
    ports = port_result.scalars().all()

    # Get connections (both incoming and outgoing)
    conn_result = await db.execute(
        select(Connection).where(
            or_(
                Connection.local_ip == host.ip_address,
                Connection.remote_ip == host.ip_address,
            )
        )
    )
    connections = conn_result.scalars().all()

    # Get ARP entries
    arp_result = await db.execute(
        select(ARPEntry).where(ARPEntry.ip_address == host.ip_address)
    )
    arp_entries = arp_result.scalars().all()

    # Get conflicts
    conflict_result = await db.execute(select(Conflict).where(Conflict.host_id == host_id))
    conflicts = conflict_result.scalars().all()

    # Calculate freshness
    freshness = calculate_freshness(host.last_seen)

    # Count open ports
    open_ports = [p for p in ports if p.state == "open"]

    return {
        "host": {
            "id": host.id,
            "ip_address": host.ip_address,
            "ip_v6_address": host.ip_v6_address,
            "mac_address": host.mac_address,
            "hostname": host.hostname,
            "fqdn": host.fqdn,
            "netbios_name": host.netbios_name,
            "os_name": host.os_name,
            "os_version": host.os_version,
            "os_family": host.os_family,
            "os_confidence": host.os_confidence,
            "device_type": host.device_type,
            "vendor": host.vendor,
            "criticality": host.criticality,
            "owner": host.owner,
            "location": host.location,
            "tags": host.tags,
            "notes": host.notes,
            "is_verified": host.is_verified,
            "is_active": host.is_active,
            "first_seen": host.first_seen.isoformat(),
            "last_seen": host.last_seen.isoformat(),
            "source_types": host.source_types or [],
        },
        "ports": {
            "total": len(ports),
            "open": len(open_ports),
            "items": [
                {
                    "id": p.id,
                    "port_number": p.port_number,
                    "protocol": p.protocol,
                    "state": p.state,
                    "service_name": p.service_name,
                    "service_version": p.service_version,
                    "product": p.product,
                    "version": p.version,
                    "confidence": p.confidence,
                    "first_seen": p.first_seen.isoformat(),
                    "last_seen": p.last_seen.isoformat(),
                    "source_types": p.source_types or [],
                }
                for p in ports
            ],
        },
        "connections": {
            "total": len(connections),
            "items": [
                {
                    "id": c.id,
                    "local_ip": c.local_ip,
                    "local_port": c.local_port,
                    "remote_ip": c.remote_ip,
                    "remote_port": c.remote_port,
                    "protocol": c.protocol,
                    "state": c.state,
                    "process_name": c.process_name,
                    "first_seen": c.first_seen.isoformat(),
                    "last_seen": c.last_seen.isoformat(),
                    "source_type": c.source_type,
                }
                for c in connections
            ],
        },
        "arp_entries": {
            "total": len(arp_entries),
            "items": [
                {
                    "id": a.id,
                    "ip_address": a.ip_address,
                    "mac_address": a.mac_address,
                    "interface": a.interface,
                    "is_resolved": a.is_resolved,
                    "first_seen": a.first_seen.isoformat(),
                    "last_seen": a.last_seen.isoformat(),
                    "source_type": a.source_type,
                }
                for a in arp_entries
            ],
        },
        "conflicts": {
            "total": len(conflicts),
            "unresolved": len([c for c in conflicts if not c.resolved]),
            "items": [
                {
                    "id": c.id,
                    "conflict_type": c.conflict_type,
                    "field": c.field,
                    "values": c.values,
                    "resolved": c.resolved,
                    "resolution": c.resolution,
                    "resolved_by": c.resolved_by,
                    "detected_at": c.detected_at.isoformat(),
                    "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
                }
                for c in conflicts
            ],
        },
        "freshness": freshness,
        "summary": {
            "total_ports": len(ports),
            "open_ports": len(open_ports),
            "total_connections": len(connections),
            "total_arp_entries": len(arp_entries),
            "unresolved_conflicts": len([c for c in conflicts if not c.resolved]),
            "is_responsive": freshness["freshness"] in ["fresh", "recent"],
            "data_coverage": {
                "has_mac": bool(host.mac_address),
                "has_os": bool(host.os_name),
                "has_hostname": bool(host.hostname),
                "has_ports": len(ports) > 0,
                "has_connections": len(connections) > 0,
                "has_arp": len(arp_entries) > 0,
            },
        },
    }


def calculate_freshness(last_seen: datetime) -> Dict:
    """
    Calculate freshness indicator for a host.

    Returns:
        Dictionary with:
        - freshness: "fresh" (<24h), "recent" (<7d), "stale" (<30d), "old" (>30d)
        - hours_ago: Hours since last_seen
        - days_ago: Days since last_seen
    """
    now = datetime.utcnow()
    delta = now - last_seen

    hours_ago = delta.total_seconds() / 3600
    days_ago = delta.days

    if hours_ago < 24:
        freshness = "fresh"
    elif days_ago < 7:
        freshness = "recent"
    elif days_ago < 30:
        freshness = "stale"
    else:
        freshness = "old"

    return {
        "freshness": freshness,
        "hours_ago": round(hours_ago, 1),
        "days_ago": days_ago,
        "last_seen": last_seen.isoformat(),
    }

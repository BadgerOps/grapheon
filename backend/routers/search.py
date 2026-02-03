"""
Full-text search API endpoints.

Provides unified search across hosts, ports, connections, and imports.
"""

import logging
import time
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, cast, String

from database import get_db
from models import Host, Port, Connection, ARPEntry, RawImport

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
async def search_all(
    q: str = Query(..., min_length=1, description="Search query"),
    types: Optional[str] = Query(None, description="Comma-separated types: hosts,ports,connections,arp,imports"),
    limit: int = Query(50, ge=1, le=500, description="Results per type"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Search across all network data.

    Searches hosts (IP, hostname, MAC, OS), ports (service name, product),
    connections (IPs, process), ARP entries, and import records.
    """
    start_time = time.perf_counter()
    logger.info("=" * 60)
    logger.info(f"SEARCH STARTED: query='{q}'")

    # Parse types filter
    search_types = set(types.split(",")) if types else {"hosts", "ports", "connections", "arp", "imports"}
    logger.info(f"Searching types: {search_types}")

    results = {
        "query": q,
        "results": {},
        "totals": {},
    }

    search_pattern = f"%{q}%"

    # Search hosts
    if "hosts" in search_types:
        step_start = time.perf_counter()
        host_query = select(Host).where(
            or_(
                Host.ip_address.ilike(search_pattern),
                Host.hostname.ilike(search_pattern),
                Host.fqdn.ilike(search_pattern),
                Host.mac_address.ilike(search_pattern),
                Host.os_name.ilike(search_pattern),
                Host.vendor.ilike(search_pattern),
                Host.netbios_name.ilike(search_pattern),
                Host.notes.ilike(search_pattern),
            )
        ).limit(limit)

        host_result = await db.execute(host_query)
        hosts = host_result.scalars().all()

        results["results"]["hosts"] = [
            {
                "id": h.id,
                "ip_address": h.ip_address,
                "hostname": h.hostname,
                "mac_address": h.mac_address,
                "os_name": h.os_name,
                "vendor": h.vendor,
                "device_type": h.device_type,
                "last_seen": h.last_seen.isoformat() if h.last_seen else None,
                "_type": "host",
            }
            for h in hosts
        ]
        results["totals"]["hosts"] = len(hosts)
        logger.info(f"  Hosts: {len(hosts)} results in {(time.perf_counter() - step_start)*1000:.1f}ms")

    # Search ports
    if "ports" in search_types:
        step_start = time.perf_counter()
        port_query = select(Port).where(
            or_(
                Port.service_name.ilike(search_pattern),
                Port.product.ilike(search_pattern),
                Port.service_version.ilike(search_pattern),
                Port.service_extrainfo.ilike(search_pattern),
                cast(Port.port_number, String).ilike(search_pattern),
            )
        ).limit(limit)

        port_result = await db.execute(port_query)
        ports = port_result.scalars().all()

        results["results"]["ports"] = [
            {
                "id": p.id,
                "host_id": p.host_id,
                "port_number": p.port_number,
                "protocol": p.protocol,
                "state": p.state,
                "service_name": p.service_name,
                "product": p.product,
                "service_version": p.service_version,
                "_type": "port",
            }
            for p in ports
        ]
        results["totals"]["ports"] = len(ports)
        logger.info(f"  Ports: {len(ports)} results in {(time.perf_counter() - step_start)*1000:.1f}ms")

    # Search connections
    if "connections" in search_types:
        step_start = time.perf_counter()
        conn_query = select(Connection).where(
            or_(
                Connection.local_ip.ilike(search_pattern),
                Connection.remote_ip.ilike(search_pattern),
                Connection.process_name.ilike(search_pattern),
                cast(Connection.local_port, String).ilike(search_pattern),
                cast(Connection.remote_port, String).ilike(search_pattern),
            )
        ).limit(limit)

        conn_result = await db.execute(conn_query)
        connections = conn_result.scalars().all()

        results["results"]["connections"] = [
            {
                "id": c.id,
                "local_ip": c.local_ip,
                "local_port": c.local_port,
                "remote_ip": c.remote_ip,
                "remote_port": c.remote_port,
                "protocol": c.protocol,
                "state": c.state,
                "process_name": c.process_name,
                "_type": "connection",
            }
            for c in connections
        ]
        results["totals"]["connections"] = len(connections)
        logger.info(f"  Connections: {len(connections)} results in {(time.perf_counter() - step_start)*1000:.1f}ms")

    # Search ARP entries
    if "arp" in search_types:
        step_start = time.perf_counter()
        arp_query = select(ARPEntry).where(
            or_(
                ARPEntry.ip_address.ilike(search_pattern),
                ARPEntry.mac_address.ilike(search_pattern),
                ARPEntry.vendor.ilike(search_pattern),
                ARPEntry.interface.ilike(search_pattern),
            )
        ).limit(limit)

        arp_result = await db.execute(arp_query)
        arp_entries = arp_result.scalars().all()

        results["results"]["arp"] = [
            {
                "id": a.id,
                "ip_address": a.ip_address,
                "mac_address": a.mac_address,
                "vendor": a.vendor,
                "interface": a.interface,
                "_type": "arp",
            }
            for a in arp_entries
        ]
        results["totals"]["arp"] = len(arp_entries)
        logger.info(f"  ARP: {len(arp_entries)} results in {(time.perf_counter() - step_start)*1000:.1f}ms")

    # Search imports
    if "imports" in search_types:
        step_start = time.perf_counter()
        import_query = select(RawImport).where(
            or_(
                RawImport.source_type.ilike(search_pattern),
                RawImport.filename.ilike(search_pattern),
                RawImport.notes.ilike(search_pattern),
            )
        ).limit(limit)

        import_result = await db.execute(import_query)
        imports = import_result.scalars().all()

        results["results"]["imports"] = [
            {
                "id": i.id,
                "source_type": i.source_type,
                "filename": i.filename,
                "parse_status": i.parse_status,
                "parsed_count": i.parsed_count,
                "created_at": i.created_at.isoformat() if i.created_at else None,
                "_type": "import",
            }
            for i in imports
        ]
        results["totals"]["imports"] = len(imports)
        logger.info(f"  Imports: {len(imports)} results in {(time.perf_counter() - step_start)*1000:.1f}ms")

    # Calculate total
    total_results = sum(results["totals"].values())
    results["total_results"] = total_results

    total_duration = (time.perf_counter() - start_time) * 1000
    results["search_time_ms"] = round(total_duration, 1)

    logger.info("=" * 60)
    logger.info(f"SEARCH COMPLETE: {total_results} total results in {total_duration:.1f}ms")
    logger.info("=" * 60)

    return results


@router.get("/hosts")
async def search_hosts(
    q: str = Query(..., min_length=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Search only hosts with pagination."""
    search_pattern = f"%{q}%"

    # Count total
    count_query = select(func.count(Host.id)).where(
        or_(
            Host.ip_address.ilike(search_pattern),
            Host.hostname.ilike(search_pattern),
            Host.mac_address.ilike(search_pattern),
            Host.os_name.ilike(search_pattern),
        )
    )
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    # Get results
    query = select(Host).where(
        or_(
            Host.ip_address.ilike(search_pattern),
            Host.hostname.ilike(search_pattern),
            Host.mac_address.ilike(search_pattern),
            Host.os_name.ilike(search_pattern),
        )
    ).offset(skip).limit(limit)

    result = await db.execute(query)
    hosts = result.scalars().all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [
            {
                "id": h.id,
                "ip_address": h.ip_address,
                "hostname": h.hostname,
                "mac_address": h.mac_address,
                "os_name": h.os_name,
                "device_type": h.device_type,
            }
            for h in hosts
        ],
    }


@router.get("/suggestions")
async def get_suggestions(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get autocomplete suggestions for search.

    Returns distinct values that match the query from various fields.
    """
    search_pattern = f"{q}%"  # Prefix match for suggestions
    suggestions = []

    # IP addresses
    ip_query = select(Host.ip_address).where(
        Host.ip_address.ilike(search_pattern)
    ).distinct().limit(limit)
    ip_result = await db.execute(ip_query)
    for ip in ip_result.scalars():
        suggestions.append({"value": ip, "type": "ip"})

    # Hostnames
    hostname_query = select(Host.hostname).where(
        Host.hostname.ilike(search_pattern),
        Host.hostname.isnot(None),
    ).distinct().limit(limit)
    hostname_result = await db.execute(hostname_query)
    for hostname in hostname_result.scalars():
        suggestions.append({"value": hostname, "type": "hostname"})

    # Service names
    service_query = select(Port.service_name).where(
        Port.service_name.ilike(search_pattern),
        Port.service_name.isnot(None),
    ).distinct().limit(limit)
    service_result = await db.execute(service_query)
    for service in service_result.scalars():
        suggestions.append({"value": service, "type": "service"})

    # MAC vendors
    vendor_query = select(Host.vendor).where(
        Host.vendor.ilike(search_pattern),
        Host.vendor.isnot(None),
    ).distinct().limit(limit)
    vendor_result = await db.execute(vendor_query)
    for vendor in vendor_result.scalars():
        suggestions.append({"value": vendor, "type": "vendor"})

    return {
        "query": q,
        "suggestions": suggestions[:limit],
    }

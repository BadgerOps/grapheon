"""
Data export API endpoints.

Provides CSV and JSON export for hosts, ports, connections, and full database dumps.
"""

import logging
import time
import csv
import io
import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import Host, Port, Connection, ARPEntry

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

router = APIRouter(prefix="/api/export", tags=["export"])


def generate_filename(prefix: str, format: str) -> str:
    """Generate a timestamped filename."""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}.{format}"


@router.get("/hosts")
async def export_hosts(
    format: str = Query("csv", enum=["csv", "json"], description="Export format"),
    include_ports: bool = Query(False, description="Include ports in export"),
    active_only: bool = Query(True, description="Only export active hosts"),
    db: AsyncSession = Depends(get_db),
):
    """
    Export all hosts to CSV or JSON.
    """
    start_time = time.perf_counter()
    logger.info(f"EXPORT HOSTS: format={format}, include_ports={include_ports}")

    # Query hosts
    query = select(Host)
    if active_only:
        query = query.where(Host.is_active.is_(True))

    result = await db.execute(query.order_by(Host.ip_address))
    hosts = result.scalars().all()

    logger.info(f"Exporting {len(hosts)} hosts")

    if format == "json":
        # JSON export
        data = []
        for host in hosts:
            host_data = {
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
                "first_seen": host.first_seen.isoformat() if host.first_seen else None,
                "last_seen": host.last_seen.isoformat() if host.last_seen else None,
                "source_types": host.source_types,
            }

            if include_ports:
                port_result = await db.execute(
                    select(Port).where(Port.host_id == host.id)
                )
                ports = port_result.scalars().all()
                host_data["ports"] = [
                    {
                        "port_number": p.port_number,
                        "protocol": p.protocol,
                        "state": p.state,
                        "service_name": p.service_name,
                        "service_version": p.service_version,
                        "product": p.product,
                    }
                    for p in ports
                ]

            data.append(host_data)

        json_content = json.dumps(data, indent=2)
        filename = generate_filename("hosts", "json")

        logger.info(f"Export complete in {(time.perf_counter() - start_time)*1000:.1f}ms")

        return Response(
            content=json_content,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    else:
        # CSV export
        output = io.StringIO()
        fieldnames = [
            "ip_address", "mac_address", "hostname", "fqdn", "os_name",
            "os_version", "os_family", "device_type", "vendor", "criticality",
            "owner", "location", "first_seen", "last_seen", "source_types",
        ]

        if include_ports:
            fieldnames.append("open_ports")

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for host in hosts:
            row = {
                "ip_address": host.ip_address,
                "mac_address": host.mac_address,
                "hostname": host.hostname,
                "fqdn": host.fqdn,
                "os_name": host.os_name,
                "os_version": host.os_version,
                "os_family": host.os_family,
                "device_type": host.device_type,
                "vendor": host.vendor,
                "criticality": host.criticality,
                "owner": host.owner,
                "location": host.location,
                "first_seen": host.first_seen.isoformat() if host.first_seen else "",
                "last_seen": host.last_seen.isoformat() if host.last_seen else "",
                "source_types": ",".join(host.source_types or []),
            }

            if include_ports:
                port_result = await db.execute(
                    select(Port).where(Port.host_id == host.id, Port.state == "open")
                )
                ports = port_result.scalars().all()
                row["open_ports"] = ";".join(
                    f"{p.port_number}/{p.protocol}" for p in ports
                )

            writer.writerow(row)

        csv_content = output.getvalue()
        filename = generate_filename("hosts", "csv")

        logger.info(f"Export complete in {(time.perf_counter() - start_time)*1000:.1f}ms")

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )


@router.get("/ports")
async def export_ports(
    format: str = Query("csv", enum=["csv", "json"]),
    state: Optional[str] = Query(None, description="Filter by state (open, closed, filtered)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Export all ports to CSV or JSON.
    """
    logger.info(f"EXPORT PORTS: format={format}, state={state}")

    query = select(Port, Host.ip_address, Host.hostname).join(Host)
    if state:
        query = query.where(Port.state == state)

    result = await db.execute(query.order_by(Host.ip_address, Port.port_number))
    rows = result.all()

    logger.info(f"Exporting {len(rows)} ports")

    if format == "json":
        data = [
            {
                "host_ip": row.ip_address,
                "host_name": row.hostname,
                "port_number": row.Port.port_number,
                "protocol": row.Port.protocol,
                "state": row.Port.state,
                "service_name": row.Port.service_name,
                "service_version": row.Port.service_version,
                "product": row.Port.product,
                "confidence": row.Port.confidence,
                "first_seen": row.Port.first_seen.isoformat() if row.Port.first_seen else None,
                "last_seen": row.Port.last_seen.isoformat() if row.Port.last_seen else None,
            }
            for row in rows
        ]

        filename = generate_filename("ports", "json")
        return Response(
            content=json.dumps(data, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    else:
        output = io.StringIO()
        fieldnames = [
            "host_ip", "host_name", "port_number", "protocol", "state",
            "service_name", "service_version", "product", "first_seen", "last_seen",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            writer.writerow({
                "host_ip": row.ip_address,
                "host_name": row.hostname,
                "port_number": row.Port.port_number,
                "protocol": row.Port.protocol,
                "state": row.Port.state,
                "service_name": row.Port.service_name,
                "service_version": row.Port.service_version,
                "product": row.Port.product,
                "first_seen": row.Port.first_seen.isoformat() if row.Port.first_seen else "",
                "last_seen": row.Port.last_seen.isoformat() if row.Port.last_seen else "",
            })

        filename = generate_filename("ports", "csv")
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )


@router.get("/connections")
async def export_connections(
    format: str = Query("csv", enum=["csv", "json"]),
    state: Optional[str] = Query(None, description="Filter by state (ESTABLISHED, LISTEN, etc)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Export all connections to CSV or JSON.
    """
    logger.info(f"EXPORT CONNECTIONS: format={format}")

    query = select(Connection)
    if state:
        query = query.where(Connection.state == state)

    result = await db.execute(query)
    connections = result.scalars().all()

    logger.info(f"Exporting {len(connections)} connections")

    if format == "json":
        data = [
            {
                "id": c.id,
                "local_ip": c.local_ip,
                "local_port": c.local_port,
                "remote_ip": c.remote_ip,
                "remote_port": c.remote_port,
                "protocol": c.protocol,
                "state": c.state,
                "pid": c.pid,
                "process_name": c.process_name,
                "first_seen": c.first_seen.isoformat() if c.first_seen else None,
                "last_seen": c.last_seen.isoformat() if c.last_seen else None,
            }
            for c in connections
        ]

        filename = generate_filename("connections", "json")
        return Response(
            content=json.dumps(data, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    else:
        output = io.StringIO()
        fieldnames = [
            "local_ip", "local_port", "remote_ip", "remote_port",
            "protocol", "state", "pid", "process_name", "first_seen", "last_seen",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for c in connections:
            writer.writerow({
                "local_ip": c.local_ip,
                "local_port": c.local_port,
                "remote_ip": c.remote_ip,
                "remote_port": c.remote_port,
                "protocol": c.protocol,
                "state": c.state,
                "pid": c.pid,
                "process_name": c.process_name,
                "first_seen": c.first_seen.isoformat() if c.first_seen else "",
                "last_seen": c.last_seen.isoformat() if c.last_seen else "",
            })

        filename = generate_filename("connections", "csv")
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )


@router.get("/full")
async def export_full_database(
    format: str = Query("json", enum=["json"]),
    db: AsyncSession = Depends(get_db),
):
    """
    Export complete database dump as JSON.
    """
    start_time = time.perf_counter()
    logger.info("EXPORT FULL DATABASE")

    # Get all data
    hosts_result = await db.execute(select(Host).where(Host.is_active.is_(True)))
    hosts = hosts_result.scalars().all()

    ports_result = await db.execute(select(Port))
    ports = ports_result.scalars().all()

    conn_result = await db.execute(select(Connection))
    connections = conn_result.scalars().all()

    arp_result = await db.execute(select(ARPEntry))
    arp_entries = arp_result.scalars().all()

    data = {
        "export_date": datetime.utcnow().isoformat(),
        "version": "1.0",
        "counts": {
            "hosts": len(hosts),
            "ports": len(ports),
            "connections": len(connections),
            "arp_entries": len(arp_entries),
        },
        "hosts": [
            {
                "id": h.id,
                "ip_address": h.ip_address,
                "mac_address": h.mac_address,
                "hostname": h.hostname,
                "os_name": h.os_name,
                "os_family": h.os_family,
                "device_type": h.device_type,
                "vendor": h.vendor,
                "first_seen": h.first_seen.isoformat() if h.first_seen else None,
                "last_seen": h.last_seen.isoformat() if h.last_seen else None,
                "source_types": h.source_types,
            }
            for h in hosts
        ],
        "ports": [
            {
                "host_id": p.host_id,
                "port_number": p.port_number,
                "protocol": p.protocol,
                "state": p.state,
                "service_name": p.service_name,
                "product": p.product,
            }
            for p in ports
        ],
        "connections": [
            {
                "local_ip": c.local_ip,
                "local_port": c.local_port,
                "remote_ip": c.remote_ip,
                "remote_port": c.remote_port,
                "protocol": c.protocol,
                "state": c.state,
                "process_name": c.process_name,
            }
            for c in connections
        ],
        "arp_entries": [
            {
                "ip_address": a.ip_address,
                "mac_address": a.mac_address,
                "vendor": a.vendor,
                "interface": a.interface,
            }
            for a in arp_entries
        ],
    }

    filename = generate_filename("network_aggregator_full", "json")

    logger.info(f"Full export complete: {len(hosts)} hosts, {len(ports)} ports in {(time.perf_counter() - start_time)*1000:.1f}ms")

    return Response(
        content=json.dumps(data, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

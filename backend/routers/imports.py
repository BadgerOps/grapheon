from typing import List, Optional
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from ipaddress import ip_address as parse_ip

from database import get_db
from models import RawImport, Host, Port, Connection, ARPEntry
from schemas import RawImportResponse, PaginatedResponse
from parsers import get_parser, PARSERS
from utils.tagging import (
    build_host_tags,
    build_port_tags,
    build_connection_tags,
    build_arp_tags,
    merge_tags,
)
from utils.audit import audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/imports", tags=["imports"])


def _generate_guid() -> str:
    return str(uuid.uuid4())


def _is_valid_ip(value: str) -> bool:
    try:
        parse_ip(value)
        return True
    except ValueError:
        return False


def _is_unspecified_ip(value: str) -> bool:
    try:
        return parse_ip(value).is_unspecified
    except ValueError:
        return False


async def _upsert_host_from_value(
    db: AsyncSession,
    value: Optional[str],
    source_type: str,
    mac_address: Optional[str] = None,
    hostname: Optional[str] = None,
) -> Optional[Host]:
    if not value:
        return None

    raw_value = value.strip()
    if not raw_value:
        return None

    is_ip = _is_valid_ip(raw_value)
    if is_ip and _is_unspecified_ip(raw_value):
        return None

    if is_ip:
        existing = await db.execute(select(Host).where(Host.ip_address == raw_value))
    else:
        existing = await db.execute(select(Host).where(Host.hostname == raw_value))
    host = existing.scalar_one_or_none()

    if host:
        if not host.guid:
            host.guid = _generate_guid()
        if mac_address and not host.mac_address:
            host.mac_address = mac_address
        if hostname and not host.hostname:
            host.hostname = hostname
        host.tags = merge_tags(
            host.tags,
            build_host_tags(
                ip_address=host.ip_address,
                mac_address=host.mac_address,
                hostname=host.hostname,
                fqdn=host.fqdn,
                vendor=host.vendor,
                os_family=host.os_family,
                os_name=host.os_name,
            ),
        )
        current_sources = host.source_types or []
        if source_type not in current_sources:
            host.source_types = current_sources + [source_type]
        host.last_seen = datetime.utcnow()
        return host

    ip_address = raw_value
    hostname_value = hostname
    if not is_ip:
        hostname_value = hostname_value or raw_value

    host = Host(
        ip_address=ip_address,
        hostname=hostname_value,
        mac_address=mac_address,
        source_types=[source_type],
        guid=_generate_guid(),
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
    )
    host.tags = build_host_tags(
        ip_address=host.ip_address,
        mac_address=host.mac_address,
        hostname=host.hostname,
    )
    db.add(host)
    await db.flush()
    return host


async def _process_import(
    db: AsyncSession,
    import_record: RawImport,
    source_type: str,
    raw_data: str,
) -> None:
    """Parse raw data and create database records."""

    # Check if we have a parser for this source type
    if source_type not in PARSERS:
        import_record.parse_status = "pending"
        import_record.error_message = f"No parser available for '{source_type}'. Available: {', '.join(PARSERS.keys())}"
        return

    try:
        logger.debug(f"Getting parser for source_type={source_type}")
        parser = get_parser(source_type)
        result = parser.parse(raw_data)
        logger.debug(f"Parse result: success={result.success}, hosts={len(result.hosts)}, errors={result.errors}")

        if not result.success:
            import_record.parse_status = "failed"
            import_record.error_message = "; ".join(result.errors)
            logger.error(f"Parse failed: {result.errors}")
            return

        records_created = 0

        # Use a savepoint so DB errors (IntegrityError, etc.) only roll back
        # the parsed records, not the import_record itself.
        try:
            async with db.begin_nested():
                # Process hosts and their ports
                for parsed_host in result.hosts:
                    logger.debug(f"Processing host: {parsed_host.ip_address} with {len(parsed_host.ports)} ports")
                    # Check if host already exists by IP
                    existing = await db.execute(
                        select(Host).where(Host.ip_address == parsed_host.ip_address)
                    )
                    host = existing.scalar_one_or_none()

                    if host:
                        if not host.guid:
                            host.guid = _generate_guid()
                        # Update existing host with new data
                        if parsed_host.mac_address and not host.mac_address:
                            host.mac_address = parsed_host.mac_address
                        if parsed_host.hostname and not host.hostname:
                            host.hostname = parsed_host.hostname
                        if parsed_host.vendor and not host.vendor:
                            host.vendor = parsed_host.vendor
                        if parsed_host.os_name and not host.os_name:
                            host.os_name = parsed_host.os_name
                        if parsed_host.os_family and not host.os_family:
                            host.os_family = parsed_host.os_family
                        if parsed_host.os_confidence and (not host.os_confidence or parsed_host.os_confidence > host.os_confidence):
                            host.os_confidence = parsed_host.os_confidence
                            host.os_name = parsed_host.os_name
                        if parsed_host.device_type and not host.device_type:
                            host.device_type = parsed_host.device_type

                        # Update source_types
                        current_sources = host.source_types or []
                        if source_type not in current_sources:
                            host.source_types = current_sources + [source_type]

                        host.last_seen = datetime.utcnow()
                        host.tags = merge_tags(
                            host.tags,
                            build_host_tags(
                                ip_address=host.ip_address,
                                mac_address=host.mac_address,
                                hostname=host.hostname,
                                fqdn=host.fqdn,
                                vendor=host.vendor,
                                os_family=host.os_family,
                                os_name=host.os_name,
                            ),
                        )
                    else:
                        # Create new host
                        host = Host(
                            ip_address=parsed_host.ip_address,
                            mac_address=parsed_host.mac_address,
                            hostname=parsed_host.hostname,
                            fqdn=parsed_host.fqdn,
                            vendor=parsed_host.vendor,
                            os_name=parsed_host.os_name,
                            os_version=parsed_host.os_version,
                            os_family=parsed_host.os_family,
                            os_confidence=parsed_host.os_confidence,
                            device_type=parsed_host.device_type,
                            source_types=[source_type],
                            guid=_generate_guid(),
                            first_seen=datetime.utcnow(),
                            last_seen=datetime.utcnow(),
                        )
                        host.tags = build_host_tags(
                            ip_address=host.ip_address,
                            mac_address=host.mac_address,
                            hostname=host.hostname,
                            fqdn=host.fqdn,
                            vendor=host.vendor,
                            os_family=host.os_family,
                            os_name=host.os_name,
                        )
                        db.add(host)
                        records_created += 1

                    await db.flush()  # Get host.id for port foreign key
                    logger.debug(f"Host flushed with id={host.id}, processing {len(parsed_host.ports)} ports")

                    # Process ports for this host
                    for parsed_port in parsed_host.ports:
                        logger.debug(f"Processing port {parsed_port.port_number}/{parsed_port.protocol}")
                        # Check if port already exists
                        existing_port = await db.execute(
                            select(Port).where(
                                Port.host_id == host.id,
                                Port.port_number == parsed_port.port_number,
                                Port.protocol == parsed_port.protocol,
                            )
                        )
                        port = existing_port.scalar_one_or_none()

                        if port:
                            # Update existing port
                            port.state = parsed_port.state
                            if parsed_port.service_name:
                                port.service_name = parsed_port.service_name
                            if parsed_port.service_version:
                                port.service_version = parsed_port.service_version
                            if parsed_port.service_product:
                                port.product = parsed_port.service_product
                            port.last_seen = datetime.utcnow()
                            port.tags = merge_tags(
                                port.tags,
                                build_port_tags(
                                    port_number=port.port_number,
                                    protocol=port.protocol,
                                    state=port.state,
                                    service_name=port.service_name,
                                    service_product=port.product,
                                    service_version=port.service_version,
                                ),
                            )
                        else:
                            # Create new port
                            port = Port(
                                host_id=host.id,
                                port_number=parsed_port.port_number,
                                protocol=parsed_port.protocol,
                                state=parsed_port.state,
                                service_name=parsed_port.service_name,
                                service_version=parsed_port.service_version,
                                product=parsed_port.service_product,
                                service_extrainfo=parsed_port.service_banner,
                                confidence=parsed_port.confidence,
                                source_types=[source_type],
                                first_seen=datetime.utcnow(),
                                last_seen=datetime.utcnow(),
                            )
                            port.tags = build_port_tags(
                                port_number=port.port_number,
                                protocol=port.protocol,
                                state=port.state,
                                service_name=port.service_name,
                                service_product=port.product,
                                service_version=port.service_version,
                            )
                            db.add(port)
                            records_created += 1

                # Process connections (from netstat)
                for parsed_conn in result.connections:
                    await _upsert_host_from_value(
                        db,
                        parsed_conn.local_ip,
                        source_type,
                    )
                    # Skip host upsert for unspecified remote IPs (LISTEN state)
                    remote_ip = parsed_conn.remote_ip or "0.0.0.0"
                    if not _is_unspecified_ip(remote_ip):
                        await _upsert_host_from_value(
                            db,
                            remote_ip,
                            source_type,
                        )
                    conn = Connection(
                        local_ip=parsed_conn.local_ip,
                        local_port=parsed_conn.local_port or 0,
                        remote_ip=remote_ip,
                        remote_port=parsed_conn.remote_port,
                        protocol=parsed_conn.protocol,
                        state=parsed_conn.state,
                        pid=parsed_conn.pid,
                        process_name=parsed_conn.process_name,
                        source_type=source_type,
                        first_seen=datetime.utcnow(),
                        last_seen=datetime.utcnow(),
                    )
                    conn.tags = build_connection_tags(
                        local_ip=conn.local_ip,
                        local_port=conn.local_port,
                        remote_ip=conn.remote_ip,
                        remote_port=conn.remote_port,
                        protocol=conn.protocol,
                        state=conn.state,
                        process_name=conn.process_name,
                    )
                    db.add(conn)
                    records_created += 1

                # Process ARP entries
                for parsed_arp in result.arp_entries:
                    await _upsert_host_from_value(
                        db,
                        parsed_arp.ip_address,
                        source_type,
                        mac_address=parsed_arp.mac_address,
                    )
                    if not parsed_arp.mac_address:
                        continue
                    # Check if entry already exists
                    existing_arp = await db.execute(
                        select(ARPEntry).where(
                            ARPEntry.ip_address == parsed_arp.ip_address,
                            ARPEntry.mac_address == parsed_arp.mac_address,
                        )
                    )
                    arp = existing_arp.scalar_one_or_none()

                    if not arp:
                        arp = ARPEntry(
                            ip_address=parsed_arp.ip_address,
                            mac_address=parsed_arp.mac_address,
                            interface=parsed_arp.interface,
                            entry_type=parsed_arp.entry_type,
                            vendor=parsed_arp.vendor,
                            source_type=source_type,
                            first_seen=datetime.utcnow(),
                        )
                        arp.tags = build_arp_tags(
                            ip_address=arp.ip_address,
                            mac_address=arp.mac_address,
                            interface=arp.interface,
                            entry_type=arp.entry_type,
                            vendor=arp.vendor,
                        )
                        db.add(arp)
                        records_created += 1

        except Exception as db_err:
            # Savepoint was rolled back automatically; outer transaction is intact.
            # The import_record (flushed before _process_import) is still valid.
            logger.exception(f"Database error while importing {source_type} data")
            import_record.parse_status = "failed"
            import_record.error_message = f"Database error: {str(db_err)}"
            return

        # Update import record (savepoint committed successfully)
        import_record.parse_status = "success" if not result.warnings else "partial"
        import_record.parsed_count = records_created
        import_record.processed_at = datetime.utcnow()

        if result.warnings:
            import_record.error_message = "; ".join(result.warnings)

    except Exception as e:
        logger.exception(f"Error parsing {source_type} data")
        import_record.parse_status = "failed"
        import_record.error_message = str(e)


@router.post("/raw", response_model=RawImportResponse, status_code=201)
async def import_raw_data(
    source_type: str = Form(...),
    raw_data: str = Form(...),
    filename: Optional[str] = Form(None),
    source_host: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Import raw network data from pasted text.

    Form parameters:
    - source_type: Type of data source (nmap, netstat, arp, traceroute, ping)
    - raw_data: The actual raw data text
    - filename: Optional filename for reference
    - tags: Optional comma-separated tags
    - notes: Optional notes about the import
    """
    logger.debug(f"POST /raw - source_type={source_type}, data_length={len(raw_data)}")
    logger.debug(f"Raw data preview: {raw_data[:200]}...")

    # Parse tags
    parsed_tags = None
    if tags:
        parsed_tags = [t.strip() for t in tags.split(",") if t.strip()]

    # Create import record
    import_record = RawImport(
        source_type=source_type,
        import_type="paste",
        filename=filename,
        source_host=source_host,
        raw_data=raw_data,
        tags=parsed_tags,
        notes=notes or (f"Source host: {source_host}" if source_host else None),
        parse_status="pending",
        created_at=datetime.utcnow(),
    )

    db.add(import_record)
    await db.flush()
    logger.debug(f"Created import record id={import_record.id}")

    # Parse the data and create records
    if source_host:
        await _upsert_host_from_value(db, source_host, "import_source")
    await _process_import(db, import_record, source_type, raw_data)
    logger.debug(f"Parse complete: status={import_record.parse_status}, count={import_record.parsed_count}")

    await db.commit()
    await db.refresh(import_record)

    logger.debug(f"Import committed successfully: id={import_record.id}")
    audit.log_import(source_type=source_type, filename=filename, status=import_record.parse_status, record_count=import_record.parsed_count or 0, error_message=import_record.error_message)
    return RawImportResponse.model_validate(import_record)


@router.post("/file", response_model=RawImportResponse, status_code=201)
async def import_file(
    file: UploadFile = File(...),
    source_type: str = Form(...),
    source_host: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Import network data from uploaded file.

    Form parameters:
    - file: The file to upload
    - source_type: Type of data source (nmap, netstat, arp, traceroute, ping)
    - tags: Optional comma-separated tags
    - notes: Optional notes about the import
    """
    # Read file content
    try:
        content = await file.read()
        raw_data = content.decode("utf-8")
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to read file: {str(e)}"
        )

    # Parse tags
    parsed_tags = None
    if tags:
        parsed_tags = [t.strip() for t in tags.split(",") if t.strip()]

    # Create import record
    import_record = RawImport(
        source_type=source_type,
        import_type="file",
        filename=file.filename,
        source_host=source_host,
        raw_data=raw_data,
        tags=parsed_tags,
        notes=notes or (f"Source host: {source_host}" if source_host else None),
        parse_status="pending",
        created_at=datetime.utcnow(),
    )

    db.add(import_record)
    await db.flush()

    # Parse the data and create records
    if source_host:
        await _upsert_host_from_value(db, source_host, "import_source")
    await _process_import(db, import_record, source_type, raw_data)

    await db.commit()
    await db.refresh(import_record)

    audit.log_import(source_type=source_type, filename=file.filename, status=import_record.parse_status, record_count=import_record.parsed_count or 0, error_message=import_record.error_message)
    return RawImportResponse.model_validate(import_record)


@router.get("", response_model=PaginatedResponse)
async def list_imports(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    source_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    List import history with pagination and optional filtering.

    Query parameters:
    - skip: Number of imports to skip (default 0)
    - limit: Number of imports to return (default 50, max 1000)
    - source_type: Optional filter by source type
    """
    # Build query
    query = select(RawImport)

    if source_type:
        query = query.where(RawImport.source_type == source_type)

    # Get total count
    count_query = select(func.count(RawImport.id))
    if source_type:
        count_query = count_query.where(RawImport.source_type == source_type)

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    # Get paginated results
    result = await db.execute(
        query.offset(skip)
        .limit(limit)
        .order_by(RawImport.created_at.desc())
    )
    imports = result.scalars().all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [RawImportResponse.model_validate(imp) for imp in imports],
    }


@router.get("/parsers", response_model=dict)
async def list_parsers():
    """List available parsers."""
    return {
        "parsers": list(PARSERS.keys()),
        "count": len(PARSERS),
    }


@router.get("/{import_id}", response_model=dict)
async def get_import(import_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get import details by ID, including raw data.
    """
    result = await db.execute(
        select(RawImport).where(RawImport.id == import_id)
    )
    import_record = result.scalar_one_or_none()

    if not import_record:
        raise HTTPException(status_code=404, detail="Import not found")

    return {
        "import": RawImportResponse.model_validate(import_record),
        "raw_data": import_record.raw_data,
    }


@router.post("/{import_id}/reparse", response_model=RawImportResponse)
async def reparse_import(import_id: int, db: AsyncSession = Depends(get_db)):
    """
    Re-parse an existing import record.
    """
    result = await db.execute(
        select(RawImport).where(RawImport.id == import_id)
    )
    import_record = result.scalar_one_or_none()

    if not import_record:
        raise HTTPException(status_code=404, detail="Import not found")

    # Re-parse the data
    await _process_import(db, import_record, import_record.source_type, import_record.raw_data)

    await db.commit()
    await db.refresh(import_record)

    return RawImportResponse.model_validate(import_record)


@router.post("/bulk", response_model=dict, status_code=201)
async def bulk_import_files(
    files: List[UploadFile] = File(...),
    source_type: str = Form(...),
    source_host: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Import multiple files at once.

    Form parameters:
    - files: Multiple files to upload
    - source_type: Type of data source (same for all files)
    - tags: Optional comma-separated tags (applied to all files)
    - notes: Optional notes (applied to all files)

    Returns summary of import results.
    """
    import time
    start_time = time.perf_counter()

    logger.info(f"BULK IMPORT: {len(files)} files, source_type={source_type}")

    # Parse tags
    parsed_tags = None
    if tags:
        parsed_tags = [t.strip() for t in tags.split(",") if t.strip()]

    results = {
        "total_files": len(files),
        "successful": 0,
        "failed": 0,
        "imports": [],
        "errors": [],
    }

    for i, file in enumerate(files):
        file_start = time.perf_counter()
        logger.info(f"[{i+1}/{len(files)}] Processing: {file.filename}")

        try:
            # Read file content
            content = await file.read()
            try:
                raw_data = content.decode("utf-8")
            except UnicodeDecodeError:
                # Try latin-1 as fallback
                raw_data = content.decode("latin-1")

            # Create import record
            import_record = RawImport(
                source_type=source_type,
                import_type="file",
                filename=file.filename,
                source_host=source_host,
                raw_data=raw_data,
                tags=parsed_tags,
                notes=notes or (f"Source host: {source_host}" if source_host else None),
                parse_status="pending",
                created_at=datetime.utcnow(),
            )

            db.add(import_record)
            await db.flush()

            # Parse the data and create records
            if source_host:
                await _upsert_host_from_value(db, source_host, "import_source")
            await _process_import(db, import_record, source_type, raw_data)

            file_duration = (time.perf_counter() - file_start) * 1000
            logger.info(
                f"[{i+1}/{len(files)}] {file.filename}: "
                f"status={import_record.parse_status}, "
                f"records={import_record.parsed_count}, "
                f"duration={file_duration:.1f}ms"
            )

            results["imports"].append({
                "id": import_record.id,
                "filename": file.filename,
                "status": import_record.parse_status,
                "parsed_count": import_record.parsed_count,
                "error": import_record.error_message,
            })

            if import_record.parse_status in ("success", "partial"):
                results["successful"] += 1
            else:
                results["failed"] += 1

        except Exception as e:
            logger.error(f"[{i+1}/{len(files)}] {file.filename}: Error - {e}")
            results["errors"].append({
                "filename": file.filename,
                "error": str(e),
            })
            results["failed"] += 1

    await db.commit()

    total_duration = (time.perf_counter() - start_time) * 1000
    results["duration_ms"] = round(total_duration, 1)

    logger.info(
        f"BULK IMPORT COMPLETE: "
        f"{results['successful']}/{results['total_files']} successful, "
        f"duration={total_duration:.1f}ms"
    )

    audit.log_import(source_type=source_type, filename=f"bulk:{len(files)} files", status="success" if results["failed"] == 0 else "partial", record_count=results["successful"])
    return results

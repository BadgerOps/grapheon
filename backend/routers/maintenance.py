"""
Database maintenance API endpoints.

Provides data aging, cleanup, database statistics, vendor lookup, and backup/restore.
"""

import logging
import os
import shutil
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from config import settings
from database import get_db
from models import Host, Port, Connection, ARPEntry, RawImport, Conflict
from services.data_aging import run_cleanup, get_data_age_stats, CleanupPolicy
from services.mac_vendor import lookup_mac_vendor, get_vendor_lookup
from utils.audit import audit

DATABASE_URL = settings.DATABASE_URL

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


@router.get("/stats")
async def get_database_stats(db: AsyncSession = Depends(get_db)):
    """
    Get overall database statistics.
    """
    logger.info("Fetching database statistics")

    # Count records in each table
    host_count = await db.execute(select(func.count(Host.id)))
    active_host_count = await db.execute(
        select(func.count(Host.id)).where(Host.is_active.is_(True))
    )
    port_count = await db.execute(select(func.count(Port.id)))
    open_port_count = await db.execute(
        select(func.count(Port.id)).where(Port.state == "open")
    )
    connection_count = await db.execute(select(func.count(Connection.id)))
    arp_count = await db.execute(select(func.count(ARPEntry.id)))
    import_count = await db.execute(select(func.count(RawImport.id)))
    conflict_count = await db.execute(select(func.count(Conflict.id)))
    unresolved_conflict_count = await db.execute(
        select(func.count(Conflict.id)).where(Conflict.resolved.is_(False))
    )

    # Get data age stats
    age_stats = await get_data_age_stats(db)

    return {
        "counts": {
            "hosts": {
                "total": host_count.scalar() or 0,
                "active": active_host_count.scalar() or 0,
            },
            "ports": {
                "total": port_count.scalar() or 0,
                "open": open_port_count.scalar() or 0,
            },
            "connections": connection_count.scalar() or 0,
            "arp_entries": arp_count.scalar() or 0,
            "imports": import_count.scalar() or 0,
            "conflicts": {
                "total": conflict_count.scalar() or 0,
                "unresolved": unresolved_conflict_count.scalar() or 0,
            },
        },
        "age_distribution": age_stats,
    }


@router.post("/cleanup/preview")
async def preview_cleanup(
    host_stale_days: int = Query(30, ge=1, description="Days after which hosts are considered stale"),
    host_archive_days: int = Query(90, ge=1, description="Days after which hosts are deactivated"),
    connection_max_age_days: int = Query(7, ge=1, description="Days to keep connections"),
    arp_max_age_days: int = Query(7, ge=1, description="Days to keep ARP entries"),
    import_max_age_days: int = Query(30, ge=1, description="Days to keep import raw data"),
    db: AsyncSession = Depends(get_db),
):
    """
    Preview what would be cleaned up without making changes (dry run).
    """
    logger.info("Running cleanup preview (dry run)")

    policy = CleanupPolicy(
        host_stale_days=host_stale_days,
        host_archive_days=host_archive_days,
        connection_max_age_days=connection_max_age_days,
        arp_max_age_days=arp_max_age_days,
        import_max_age_days=import_max_age_days,
    )

    result = await run_cleanup(db, policy=policy, dry_run=True)

    return {
        "dry_run": True,
        "policy": {
            "host_stale_days": policy.host_stale_days,
            "host_archive_days": policy.host_archive_days,
            "connection_max_age_days": policy.connection_max_age_days,
            "arp_max_age_days": policy.arp_max_age_days,
            "import_max_age_days": policy.import_max_age_days,
        },
        "would_affect": {
            "hosts_marked_stale": result.hosts_marked_stale,
            "hosts_deactivated": result.hosts_deactivated,
            "connections_deleted": result.connections_deleted,
            "arp_entries_deleted": result.arp_entries_deleted,
            "imports_cleaned": result.imports_cleaned,
            "conflicts_deleted": result.conflicts_deleted,
            "orphaned_ports_deleted": result.orphaned_ports_deleted,
        },
        "duration_ms": result.duration_ms,
    }


@router.post("/cleanup/run")
async def run_cleanup_now(
    host_stale_days: int = Query(30, ge=1),
    host_archive_days: int = Query(90, ge=1),
    connection_max_age_days: int = Query(7, ge=1),
    arp_max_age_days: int = Query(7, ge=1),
    import_max_age_days: int = Query(30, ge=1),
    db: AsyncSession = Depends(get_db),
):
    """
    Run data cleanup with specified policy.

    WARNING: This permanently deletes data!
    """
    logger.info("Running cleanup (LIVE)")

    policy = CleanupPolicy(
        host_stale_days=host_stale_days,
        host_archive_days=host_archive_days,
        connection_max_age_days=connection_max_age_days,
        arp_max_age_days=arp_max_age_days,
        import_max_age_days=import_max_age_days,
    )

    result = await run_cleanup(db, policy=policy, dry_run=False)

    return {
        "success": True,
        "dry_run": False,
        "cleaned": {
            "hosts_marked_stale": result.hosts_marked_stale,
            "hosts_deactivated": result.hosts_deactivated,
            "connections_deleted": result.connections_deleted,
            "arp_entries_deleted": result.arp_entries_deleted,
            "imports_cleaned": result.imports_cleaned,
            "conflicts_deleted": result.conflicts_deleted,
            "orphaned_ports_deleted": result.orphaned_ports_deleted,
        },
        "duration_ms": result.duration_ms,
        "timestamp": result.timestamp.isoformat(),
    }


@router.get("/health")
async def database_health(db: AsyncSession = Depends(get_db)):
    """
    Check database health and connectivity.
    """
    try:
        # Simple query to verify database is accessible
        result = await db.execute(select(func.count(Host.id)))
        count = result.scalar()

        return {
            "status": "healthy",
            "database": "connected",
            "host_count": count,
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "database": "error",
            "error": str(e),
        }


@router.post("/vendor-lookup")
async def update_vendor_info(
    overwrite: bool = Query(False, description="Overwrite existing vendor info"),
    db: AsyncSession = Depends(get_db),
):
    """
    Update vendor information for all hosts with MAC addresses.

    Uses the built-in OUI database to lookup vendors.
    """
    logger.info(f"Running vendor lookup (overwrite={overwrite})")

    # Get hosts with MAC addresses
    if overwrite:
        query = select(Host).where(Host.mac_address.isnot(None))
    else:
        query = select(Host).where(
            Host.mac_address.isnot(None),
            Host.vendor.is_(None)
        )

    result = await db.execute(query)
    hosts = result.scalars().all()

    updated = 0
    local_admin = 0
    not_found = 0

    for host in hosts:
        vendor = lookup_mac_vendor(host.mac_address)
        if vendor == "Locally Administered":
            host.vendor = vendor
            local_admin += 1
        elif vendor:
            host.vendor = vendor
            updated += 1
        else:
            not_found += 1

    await db.commit()

    return {
        "success": True,
        "hosts_checked": len(hosts),
        "vendors_updated": updated,
        "vendors_local_admin": local_admin,
        "vendors_not_found": not_found,
    }


@router.get("/vendor-lookup/{mac}")
async def lookup_single_vendor(mac: str):
    """
    Lookup vendor for a single MAC address.
    """
    vendor_lookup = get_vendor_lookup()
    normalized = vendor_lookup.normalize_mac(mac)

    if not normalized:
        raise HTTPException(status_code=400, detail="Invalid MAC address format")

    vendor = vendor_lookup.lookup(mac)

    return {
        "mac_address": normalized,
        "oui": vendor_lookup.get_oui(mac),
        "vendor": vendor,
    }


@router.post("/backup")
async def create_backup(db: AsyncSession = Depends(get_db)):
    """
    Create a backup of the database.

    Returns a downloadable backup file.
    """
    logger.info("Creating database backup")

    # Extract database path from URL
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite+aiosqlite:///", "")
    if not db_path.startswith("/"):
        db_path = os.path.join(os.getcwd(), db_path)

    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="Database file not found")

    # Create backup directory
    backup_dir = os.path.join(os.path.dirname(db_path), "backups")
    os.makedirs(backup_dir, exist_ok=True)

    # Generate backup filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"network_backup_{timestamp}.db"
    backup_path = os.path.join(backup_dir, backup_filename)

    # Copy database file
    try:
        shutil.copy2(db_path, backup_path)
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")

    # Get backup file size
    backup_size = os.path.getsize(backup_path)

    audit.log_backup_restore(operation="backup", filename=backup_filename)

    return {
        "success": True,
        "backup_file": backup_filename,
        "backup_path": backup_path,
        "size_bytes": backup_size,
        "timestamp": timestamp,
    }


@router.get("/backup/download/{filename}")
async def download_backup(filename: str):
    """
    Download a backup file.
    """
    # Extract database path from URL
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite+aiosqlite:///", "")
    if not db_path.startswith("/"):
        db_path = os.path.join(os.getcwd(), db_path)

    backup_dir = os.path.join(os.path.dirname(db_path), "backups")
    backup_path = os.path.join(backup_dir, filename)

    # Security: prevent path traversal
    if not os.path.abspath(backup_path).startswith(os.path.abspath(backup_dir)):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(backup_path):
        raise HTTPException(status_code=404, detail="Backup file not found")

    return FileResponse(
        path=backup_path,
        filename=filename,
        media_type="application/octet-stream",
    )


@router.get("/backup/list")
async def list_backups():
    """
    List available backup files.
    """
    # Extract database path from URL
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite+aiosqlite:///", "")
    if not db_path.startswith("/"):
        db_path = os.path.join(os.getcwd(), db_path)

    backup_dir = os.path.join(os.path.dirname(db_path), "backups")

    if not os.path.exists(backup_dir):
        return {"backups": [], "count": 0}

    backups = []
    for f in os.listdir(backup_dir):
        if f.endswith(".db"):
            fpath = os.path.join(backup_dir, f)
            backups.append({
                "filename": f,
                "size_bytes": os.path.getsize(fpath),
                "created_at": datetime.fromtimestamp(os.path.getctime(fpath)).isoformat(),
            })

    # Sort by creation time, newest first
    backups.sort(key=lambda x: x["created_at"], reverse=True)

    return {"backups": backups, "count": len(backups)}


@router.post("/restore/{filename}")
async def restore_backup(filename: str):
    """
    Restore database from a backup file.

    WARNING: This will replace the current database!
    """
    logger.warning(f"Restoring database from backup: {filename}")

    # Extract database path from URL
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite+aiosqlite:///", "")
    if not db_path.startswith("/"):
        db_path = os.path.join(os.getcwd(), db_path)

    backup_dir = os.path.join(os.path.dirname(db_path), "backups")
    backup_path = os.path.join(backup_dir, filename)

    # Security: prevent path traversal
    if not os.path.abspath(backup_path).startswith(os.path.abspath(backup_dir)):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(backup_path):
        raise HTTPException(status_code=404, detail="Backup file not found")

    # Create a backup of current database before restore
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    pre_restore_backup = os.path.join(backup_dir, f"pre_restore_{timestamp}.db")

    try:
        # Backup current database
        if os.path.exists(db_path):
            shutil.copy2(db_path, pre_restore_backup)

        # Restore from backup
        shutil.copy2(backup_path, db_path)

    except Exception as e:
        logger.error(f"Restore failed: {e}")
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")

    audit.log_backup_restore(operation="restore", filename=filename)

    return {
        "success": True,
        "restored_from": filename,
        "pre_restore_backup": f"pre_restore_{timestamp}.db",
        "message": "Database restored. You may need to restart the application.",
    }


@router.delete("/backup/{filename}")
async def delete_backup(filename: str):
    """
    Delete a backup file.
    """
    # Extract database path from URL
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite+aiosqlite:///", "")
    if not db_path.startswith("/"):
        db_path = os.path.join(os.getcwd(), db_path)

    backup_dir = os.path.join(os.path.dirname(db_path), "backups")
    backup_path = os.path.join(backup_dir, filename)

    # Security: prevent path traversal
    if not os.path.abspath(backup_path).startswith(os.path.abspath(backup_dir)):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(backup_path):
        raise HTTPException(status_code=404, detail="Backup file not found")

    try:
        os.remove(backup_path)
    except Exception as e:
        logger.error(f"Delete backup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

    return {"success": True, "deleted": filename}


@router.post("/backup/upload")
async def upload_backup(file: UploadFile = File(...)):
    """
    Upload a backup file (.db) from the client to the server's backup directory.

    The uploaded file will appear in the backup list and can then be restored.
    """
    logger.info(f"Uploading backup file: {file.filename}")

    # Validate file extension
    if not file.filename or not file.filename.endswith(".db"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only .db (SQLite database) files are accepted.",
        )

    # Validate filename (prevent path traversal)
    safe_filename = os.path.basename(file.filename)
    if not safe_filename or safe_filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Extract database path from URL
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite+aiosqlite:///", "")
    if not db_path.startswith("/"):
        db_path = os.path.join(os.getcwd(), db_path)

    backup_dir = os.path.join(os.path.dirname(db_path), "backups")
    os.makedirs(backup_dir, exist_ok=True)

    dest_path = os.path.join(backup_dir, safe_filename)

    # If a file with the same name exists, add a timestamp suffix
    if os.path.exists(dest_path):
        name, ext = os.path.splitext(safe_filename)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{name}_{timestamp}{ext}"
        dest_path = os.path.join(backup_dir, safe_filename)

    try:
        contents = await file.read()
        with open(dest_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        logger.error(f"Failed to save uploaded backup: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        await file.close()

    file_size = os.path.getsize(dest_path)

    audit.log_backup_restore(operation="upload", filename=safe_filename)

    return {
        "success": True,
        "filename": safe_filename,
        "size_bytes": file_size,
        "message": f"Backup '{safe_filename}' uploaded successfully. You can now restore from it.",
    }


@router.post("/seed-demo")
async def seed_demo_data(
    append: bool = Query(False, description="Append to existing data instead of clearing"),
):
    """
    Generate demo/test data by running the built-in seed script.

    WARNING: Without --append this will clear all existing data!
    """
    import subprocess

    logger.info(f"Seeding demo data (append={append})")

    # Locate the seed script
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script_path = os.path.join(backend_dir, "scripts", "seed_demo_data.py")

    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail="Seed script not found")

    # Determine database path
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite+aiosqlite:///", "")
    if not db_path.startswith("/"):
        db_path = os.path.join(os.getcwd(), db_path)

    # Build command
    cmd = ["python3", script_path, "--db", db_path]
    if append:
        cmd.append("--append")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=backend_dir,
        )

        if result.returncode != 0:
            logger.error(f"Seed script failed: {result.stderr}")
            raise HTTPException(
                status_code=500,
                detail=f"Seed script failed: {result.stderr.strip() or result.stdout.strip()}",
            )

        audit.log_seed_data(status="success", append_mode=append)

        return {
            "success": True,
            "append": append,
            "output": result.stdout.strip(),
            "message": "Demo data generated successfully. Refresh the page to see the new data.",
        }

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Seed script timed out after 60 seconds")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Python3 not found on the server")

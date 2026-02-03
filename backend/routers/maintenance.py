"""
Database maintenance API endpoints.

Provides data aging, cleanup, and database statistics.
"""

import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database import get_db
from models import Host, Port, Connection, ARPEntry, RawImport, Conflict
from services.data_aging import run_cleanup, get_data_age_stats, CleanupPolicy

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

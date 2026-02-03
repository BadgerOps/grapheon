"""
Data aging and cleanup service.

Handles:
- Marking stale hosts as inactive
- Archiving old data
- Cleaning up orphaned records
- Database maintenance
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_

from models import Host, Port, Connection, ARPEntry, RawImport, Conflict

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@dataclass
class CleanupPolicy:
    """Configuration for data cleanup."""
    # Host aging
    host_stale_days: int = 30  # Mark hosts as stale after this many days
    host_archive_days: int = 90  # Archive/deactivate hosts after this many days

    # Connection cleanup
    connection_max_age_days: int = 7  # Remove old connections

    # ARP cleanup
    arp_max_age_days: int = 7  # Remove old ARP entries

    # Import cleanup
    import_max_age_days: int = 30  # Remove old raw import data
    keep_import_metadata: bool = True  # Keep import records, just clear raw_data

    # Conflict cleanup
    conflict_resolved_max_age_days: int = 30  # Remove old resolved conflicts


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""
    hosts_marked_stale: int = 0
    hosts_deactivated: int = 0
    connections_deleted: int = 0
    arp_entries_deleted: int = 0
    imports_cleaned: int = 0
    conflicts_deleted: int = 0
    orphaned_ports_deleted: int = 0
    duration_ms: float = 0
    timestamp: datetime = None


async def run_cleanup(
    db: AsyncSession,
    policy: Optional[CleanupPolicy] = None,
    dry_run: bool = False,
) -> CleanupResult:
    """
    Run full data cleanup based on policy.

    Args:
        db: Database session
        policy: Cleanup policy (uses defaults if None)
        dry_run: If True, report what would be done without making changes

    Returns:
        CleanupResult with counts of affected records
    """
    import time
    start_time = time.perf_counter()

    if policy is None:
        policy = CleanupPolicy()

    result = CleanupResult(timestamp=datetime.utcnow())

    logger.info("=" * 60)
    logger.info(f"DATA CLEANUP STARTED (dry_run={dry_run})")
    logger.info(f"Policy: stale={policy.host_stale_days}d, archive={policy.host_archive_days}d")
    logger.info("=" * 60)

    now = datetime.utcnow()

    # 1. Mark stale hosts
    stale_cutoff = now - timedelta(days=policy.host_stale_days)
    stale_query = select(func.count(Host.id)).where(
        and_(
            Host.is_active.is_(True),
            Host.last_seen < stale_cutoff,
        )
    )
    stale_count_result = await db.execute(stale_query)
    result.hosts_marked_stale = stale_count_result.scalar() or 0

    if not dry_run and result.hosts_marked_stale > 0:
        # We don't change is_active for stale, just count them
        # Stale is informational - they're still active but not recently seen
        pass

    logger.info(f"[1/7] Stale hosts (>{policy.host_stale_days}d): {result.hosts_marked_stale}")

    # 2. Deactivate archived hosts
    archive_cutoff = now - timedelta(days=policy.host_archive_days)
    archive_query = select(func.count(Host.id)).where(
        and_(
            Host.is_active.is_(True),
            Host.last_seen < archive_cutoff,
        )
    )
    archive_count_result = await db.execute(archive_query)
    result.hosts_deactivated = archive_count_result.scalar() or 0

    if not dry_run and result.hosts_deactivated > 0:
        await db.execute(
            update(Host)
            .where(and_(Host.is_active.is_(True), Host.last_seen < archive_cutoff))
            .values(is_active=False)
        )

    logger.info(f"[2/7] Hosts to deactivate (>{policy.host_archive_days}d): {result.hosts_deactivated}")

    # 3. Delete old connections
    conn_cutoff = now - timedelta(days=policy.connection_max_age_days)
    conn_count_query = select(func.count(Connection.id)).where(
        Connection.last_seen < conn_cutoff
    )
    conn_count_result = await db.execute(conn_count_query)
    result.connections_deleted = conn_count_result.scalar() or 0

    if not dry_run and result.connections_deleted > 0:
        await db.execute(
            delete(Connection).where(Connection.last_seen < conn_cutoff)
        )

    logger.info(f"[3/7] Connections to delete (>{policy.connection_max_age_days}d): {result.connections_deleted}")

    # 4. Delete old ARP entries
    arp_cutoff = now - timedelta(days=policy.arp_max_age_days)
    arp_count_query = select(func.count(ARPEntry.id)).where(
        ARPEntry.last_seen < arp_cutoff
    )
    arp_count_result = await db.execute(arp_count_query)
    result.arp_entries_deleted = arp_count_result.scalar() or 0

    if not dry_run and result.arp_entries_deleted > 0:
        await db.execute(
            delete(ARPEntry).where(ARPEntry.last_seen < arp_cutoff)
        )

    logger.info(f"[4/7] ARP entries to delete (>{policy.arp_max_age_days}d): {result.arp_entries_deleted}")

    # 5. Clean old imports
    import_cutoff = now - timedelta(days=policy.import_max_age_days)
    if policy.keep_import_metadata:
        # Just clear raw_data field
        import_count_query = select(func.count(RawImport.id)).where(
            and_(
                RawImport.created_at < import_cutoff,
                RawImport.raw_data.isnot(None),
            )
        )
        import_count_result = await db.execute(import_count_query)
        result.imports_cleaned = import_count_result.scalar() or 0

        if not dry_run and result.imports_cleaned > 0:
            await db.execute(
                update(RawImport)
                .where(and_(RawImport.created_at < import_cutoff, RawImport.raw_data.isnot(None)))
                .values(raw_data=None)
            )
    else:
        # Delete entire records
        import_count_query = select(func.count(RawImport.id)).where(
            RawImport.created_at < import_cutoff
        )
        import_count_result = await db.execute(import_count_query)
        result.imports_cleaned = import_count_result.scalar() or 0

        if not dry_run and result.imports_cleaned > 0:
            await db.execute(
                delete(RawImport).where(RawImport.created_at < import_cutoff)
            )

    logger.info(f"[5/7] Imports to clean (>{policy.import_max_age_days}d): {result.imports_cleaned}")

    # 6. Delete old resolved conflicts
    conflict_cutoff = now - timedelta(days=policy.conflict_resolved_max_age_days)
    conflict_count_query = select(func.count(Conflict.id)).where(
        and_(
            Conflict.resolved.is_(True),
            Conflict.resolved_at < conflict_cutoff,
        )
    )
    conflict_count_result = await db.execute(conflict_count_query)
    result.conflicts_deleted = conflict_count_result.scalar() or 0

    if not dry_run and result.conflicts_deleted > 0:
        await db.execute(
            delete(Conflict).where(
                and_(Conflict.resolved.is_(True), Conflict.resolved_at < conflict_cutoff)
            )
        )

    logger.info(f"[6/7] Resolved conflicts to delete (>{policy.conflict_resolved_max_age_days}d): {result.conflicts_deleted}")

    # 7. Delete orphaned ports (ports without a host)
    # This shouldn't happen normally but clean up just in case
    orphan_query = select(func.count(Port.id)).where(
        ~Port.host_id.in_(select(Host.id))
    )
    orphan_result = await db.execute(orphan_query)
    result.orphaned_ports_deleted = orphan_result.scalar() or 0

    if not dry_run and result.orphaned_ports_deleted > 0:
        await db.execute(
            delete(Port).where(~Port.host_id.in_(select(Host.id)))
        )

    logger.info(f"[7/7] Orphaned ports to delete: {result.orphaned_ports_deleted}")

    # Commit if not dry run
    if not dry_run:
        await db.commit()

    result.duration_ms = (time.perf_counter() - start_time) * 1000

    logger.info("=" * 60)
    logger.info(f"DATA CLEANUP {'SIMULATION' if dry_run else 'COMPLETE'}")
    logger.info(f"Duration: {result.duration_ms:.1f}ms")
    logger.info("=" * 60)

    return result


async def get_data_age_stats(db: AsyncSession) -> Dict[str, Any]:
    """
    Get statistics about data age across all tables.

    Returns counts of records by age buckets.
    """
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    stats = {}

    # Host age stats
    host_fresh = await db.execute(
        select(func.count(Host.id)).where(Host.last_seen >= day_ago)
    )
    host_week = await db.execute(
        select(func.count(Host.id)).where(
            and_(Host.last_seen >= week_ago, Host.last_seen < day_ago)
        )
    )
    host_month = await db.execute(
        select(func.count(Host.id)).where(
            and_(Host.last_seen >= month_ago, Host.last_seen < week_ago)
        )
    )
    host_old = await db.execute(
        select(func.count(Host.id)).where(Host.last_seen < month_ago)
    )

    stats["hosts"] = {
        "fresh_24h": host_fresh.scalar() or 0,
        "last_week": host_week.scalar() or 0,
        "last_month": host_month.scalar() or 0,
        "older": host_old.scalar() or 0,
    }

    # Connection age stats
    conn_fresh = await db.execute(
        select(func.count(Connection.id)).where(Connection.last_seen >= day_ago)
    )
    conn_old = await db.execute(
        select(func.count(Connection.id)).where(Connection.last_seen < day_ago)
    )

    stats["connections"] = {
        "fresh_24h": conn_fresh.scalar() or 0,
        "older": conn_old.scalar() or 0,
    }

    # Import stats
    import_total = await db.execute(select(func.count(RawImport.id)))
    import_with_data = await db.execute(
        select(func.count(RawImport.id)).where(RawImport.raw_data.isnot(None))
    )

    stats["imports"] = {
        "total": import_total.scalar() or 0,
        "with_raw_data": import_with_data.scalar() or 0,
    }

    return stats

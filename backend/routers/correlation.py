"""
API endpoints for data correlation operations.

Handles:
- Running correlation jobs
- Querying conflicts
- Merging hosts manually
- Getting unified host views
"""

import logging
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Conflict
from services import (
    correlate_hosts,
    find_conflicts,
    merge_hosts,
    resolve_conflict,
    get_host_unified_view,
)
from utils.audit import audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/correlate", tags=["correlation"])


@router.post("", response_model=Dict)
async def run_correlation(
    db: AsyncSession = Depends(get_db),
):
    """
    Run correlation job across all hosts.

    Performs:
    1. IP-based host merging
    2. MAC-based host merging
    3. Conflict detection

    Returns stats on merges performed and conflicts found.
    """
    try:
        logger.info("Received correlation request")
        result = await correlate_hosts(db)

        audit.log_correlation(status="success", hosts_merged=result.hosts_merged, conflicts_detected=result.conflicts_detected, device_identities_created=result.device_identities_created)

        return {
            "success": True,
            "data": {
                "hosts_merged": result.hosts_merged,
                "conflicts_detected": result.conflicts_detected,
                "conflicts_resolved": result.conflicts_resolved,
                "hosts_updated": result.hosts_updated,
                "device_identities_created": result.device_identities_created,
                "timestamp": result.timestamp.isoformat(),
            },
            "message": (
                f"Correlation completed: {result.hosts_merged} hosts merged, "
                f"{result.device_identities_created} device identities created, "
                f"{result.conflicts_detected} conflicts detected"
            ),
        }
    except Exception as e:
        logger.error(f"Correlation failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Correlation failed: {str(e)}")


@router.get("/conflicts", response_model=Dict)
async def list_conflicts(
    resolved: Optional[bool] = Query(None, description="Filter by resolved status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """
    List all conflicts with optional filtering.

    Query parameters:
    - resolved: Filter by resolved status (True/False/None for all)
    - skip: Number of conflicts to skip (default 0)
    - limit: Number of conflicts to return (default 100, max 1000)
    """
    try:
        if resolved is None:
            # Get all conflicts
            all_conflicts = await find_conflicts(db, resolved=False)
            all_conflicts.extend(await find_conflicts(db, resolved=True))
        else:
            all_conflicts = await find_conflicts(db, resolved=resolved)

        # Apply pagination
        paginated_conflicts = all_conflicts[skip : skip + limit]

        return {
            "total": len(all_conflicts),
            "skip": skip,
            "limit": limit,
            "items": [
                {
                    "id": c.id,
                    "host_id": c.host_id,
                    "conflict_type": c.conflict_type,
                    "field": c.field,
                    "values": c.values,
                    "resolved": c.resolved,
                    "resolution": c.resolution,
                    "resolved_by": c.resolved_by,
                    "detected_at": c.detected_at.isoformat(),
                    "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
                }
                for c in paginated_conflicts
            ],
        }
    except Exception as e:
        logger.error(f"Failed to list conflicts: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list conflicts: {str(e)}")


@router.get("/conflicts/{conflict_id}", response_model=Dict)
async def get_conflict(conflict_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get details of a specific conflict.

    Returns full conflict information including all conflicting values and metadata.
    """
    try:
        from sqlalchemy import select

        result = await db.execute(select(Conflict).where(Conflict.id == conflict_id))
        conflict = result.scalar_one_or_none()

        if not conflict:
            raise HTTPException(status_code=404, detail="Conflict not found")

        return {
            "id": conflict.id,
            "host_id": conflict.host_id,
            "conflict_type": conflict.conflict_type,
            "field": conflict.field,
            "values": conflict.values,
            "resolved": conflict.resolved,
            "resolution": conflict.resolution,
            "resolved_by": conflict.resolved_by,
            "detected_at": conflict.detected_at.isoformat(),
            "resolved_at": conflict.resolved_at.isoformat() if conflict.resolved_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get conflict: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get conflict: {str(e)}")


@router.post("/conflicts/{conflict_id}/resolve", response_model=Dict)
async def mark_conflict_resolved(
    conflict_id: int,
    resolution: str = Query(..., min_length=1, description="How the conflict was resolved"),
    resolved_by: str = Query("manual", description="Who/what resolved it"),
    db: AsyncSession = Depends(get_db),
):
    """
    Mark a conflict as resolved with a resolution description.

    Parameters:
    - conflict_id: ID of conflict to resolve
    - resolution: Description of how the conflict was resolved
    - resolved_by: Who/what resolved it (default: "manual")
    """
    try:
        conflict = await resolve_conflict(db, conflict_id, resolution, resolved_by)

        return {
            "success": True,
            "data": {
                "id": conflict.id,
                "host_id": conflict.host_id,
                "conflict_type": conflict.conflict_type,
                "field": conflict.field,
                "resolved": conflict.resolved,
                "resolution": conflict.resolution,
                "resolved_by": conflict.resolved_by,
                "resolved_at": conflict.resolved_at.isoformat() if conflict.resolved_at else None,
            },
            "message": f"Conflict {conflict_id} marked as resolved",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to resolve conflict: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to resolve conflict: {str(e)}")


@router.post("/hosts/{primary_id}/merge/{secondary_id}", response_model=Dict)
async def manually_merge_hosts(
    primary_id: int,
    secondary_id: int,
    resolved_by: str = Query("manual_merge", description="Who triggered the merge"),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually merge two hosts.

    Merges secondary_id into primary_id:
    - Reassigns all ports to primary
    - Reassigns all connections to primary
    - Merges source types
    - Keeps highest confidence OS
    - Soft-deletes secondary host

    Parameters:
    - primary_id: ID of host to keep (destination)
    - secondary_id: ID of host to merge into primary (source)
    - resolved_by: Who triggered the merge
    """
    try:
        if primary_id == secondary_id:
            raise HTTPException(status_code=400, detail="Cannot merge host with itself")

        merged_host = await merge_hosts(db, primary_id, secondary_id, resolved_by)

        return {
            "success": True,
            "data": {
                "primary_id": merged_host.id,
                "secondary_id": secondary_id,
                "merged_at": merged_host.last_seen.isoformat(),
                "source_types": merged_host.source_types,
                "ip_address": merged_host.ip_address,
            },
            "message": f"Successfully merged host {secondary_id} into {primary_id}",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to merge hosts: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to merge hosts: {str(e)}")


@router.get("/hosts/{host_id}/unified", response_model=Dict)
async def get_unified_host_view(
    host_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get a unified view of a host combining all source data.

    Returns comprehensive information:
    - Host basic info
    - All ports with service details
    - All connections
    - Related ARP entries
    - All conflicts (resolved and unresolved)
    - Data freshness metrics
    - Data coverage summary
    """
    try:
        unified_view = await get_host_unified_view(db, host_id)

        return {
            "success": True,
            "data": unified_view,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get unified view: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get unified view: {str(e)}")

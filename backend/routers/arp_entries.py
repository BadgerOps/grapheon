from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database import get_db
from auth.dependencies import require_any_authenticated
from models import ARPEntry, User
from schemas import ARPEntryResponse, PaginatedResponse

router = APIRouter(prefix="/api/arp", tags=["arp"])


@router.get("", response_model=PaginatedResponse)
async def list_arp_entries(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    ip_address: Optional[str] = Query(None),
    mac_address: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    user: User = Depends(require_any_authenticated),
    db: AsyncSession = Depends(get_db),
):
    query = select(ARPEntry)
    count_query = select(func.count(ARPEntry.id))

    if ip_address:
        query = query.where(ARPEntry.ip_address == ip_address)
        count_query = count_query.where(ARPEntry.ip_address == ip_address)
    if mac_address:
        query = query.where(ARPEntry.mac_address == mac_address)
        count_query = count_query.where(ARPEntry.mac_address == mac_address)
    if source_type:
        query = query.where(ARPEntry.source_type == source_type)
        count_query = count_query.where(ARPEntry.source_type == source_type)

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    result = await db.execute(
        query.offset(skip).limit(limit).order_by(ARPEntry.last_seen.desc())
    )
    entries = result.scalars().all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [ARPEntryResponse.model_validate(entry) for entry in entries],
    }

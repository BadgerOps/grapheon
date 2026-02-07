from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database import get_db
from auth.dependencies import require_any_authenticated
from models import Connection, User
from schemas import ConnectionResponse, PaginatedResponse

router = APIRouter(prefix="/api/connections", tags=["connections"])


@router.get("", response_model=PaginatedResponse)
async def list_connections(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    local_ip: Optional[str] = Query(None),
    remote_ip: Optional[str] = Query(None),
    protocol: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    user: User = Depends(require_any_authenticated),
    db: AsyncSession = Depends(get_db),
):
    query = select(Connection)
    count_query = select(func.count(Connection.id))

    if local_ip:
        query = query.where(Connection.local_ip == local_ip)
        count_query = count_query.where(Connection.local_ip == local_ip)
    if remote_ip:
        query = query.where(Connection.remote_ip == remote_ip)
        count_query = count_query.where(Connection.remote_ip == remote_ip)
    if protocol:
        query = query.where(Connection.protocol == protocol)
        count_query = count_query.where(Connection.protocol == protocol)
    if state:
        query = query.where(Connection.state == state)
        count_query = count_query.where(Connection.state == state)

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    result = await db.execute(
        query.offset(skip).limit(limit).order_by(Connection.last_seen.desc())
    )
    connections = result.scalars().all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [ConnectionResponse.model_validate(conn) for conn in connections],
    }

"""
API endpoints for background task status tracking.

Provides polling endpoints for async imports and correlation jobs.
"""

import logging
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from models import User
from auth.dependencies import require_any_authenticated
from services.task_queue import task_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=Dict)
async def get_task_status(
    task_id: str,
    user: User = Depends(require_any_authenticated),
):
    """
    Get the status of a background task.

    Returns task state, progress, result (if complete), or error (if failed).
    """
    task = task_queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@router.get("", response_model=Dict)
async def list_tasks(
    task_type: Optional[str] = Query(None, description="Filter by task type (import, correlation, cleanup)"),
    status: Optional[str] = Query(None, description="Filter by status (pending, running, success, failed)"),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_any_authenticated),
):
    """
    List recent background tasks with optional filtering.
    """
    from services.task_queue import TaskStatus

    status_filter = None
    if status:
        try:
            status_filter = TaskStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    tasks = task_queue.list_tasks(task_type=task_type, status=status_filter, limit=limit)
    return {
        "total": len(tasks),
        "items": [t.to_dict() for t in tasks],
    }

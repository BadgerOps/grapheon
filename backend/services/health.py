"""
Health check service for Graphēon.

Checks database connectivity, upload directory writability, and tracks uptime.
Returns structured health responses with per-component status.
"""

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import text

from config import settings
from database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Captured at module load — used to compute uptime
_start_time = time.monotonic()


class ComponentHealth(BaseModel):
    name: str
    status: str  # "ok" | "degraded" | "error"
    message: Optional[str] = None
    response_time_ms: Optional[float] = None


class HealthResponse(BaseModel):
    status: str  # "healthy" | "degraded" | "unhealthy"
    app: str
    version: str
    uptime_seconds: float
    checks: list[ComponentHealth]
    timestamp: str


async def check_database() -> ComponentHealth:
    """Check database connectivity by running SELECT 1."""
    start = time.perf_counter()
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        elapsed = (time.perf_counter() - start) * 1000
        return ComponentHealth(
            name="database",
            status="ok",
            response_time_ms=round(elapsed, 1),
        )
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        return ComponentHealth(
            name="database",
            status="error",
            message=str(e),
            response_time_ms=round(elapsed, 1),
        )


def check_upload_dir() -> ComponentHealth:
    """Check that the upload directory exists and is writable."""
    upload_path = Path(settings.UPLOAD_DIR)
    if not upload_path.exists():
        return ComponentHealth(
            name="upload_directory",
            status="error",
            message=f"Directory does not exist: {upload_path}",
        )
    if not upload_path.is_dir():
        return ComponentHealth(
            name="upload_directory",
            status="error",
            message=f"Path is not a directory: {upload_path}",
        )
    if not os.access(upload_path, os.W_OK):
        return ComponentHealth(
            name="upload_directory",
            status="error",
            message=f"Directory is not writable: {upload_path}",
        )
    return ComponentHealth(
        name="upload_directory",
        status="ok",
    )


async def run_health_checks() -> HealthResponse:
    """Run all health checks and return aggregated status."""
    checks = [
        await check_database(),
        check_upload_dir(),
    ]

    # Database is critical — if it's down, the service is unhealthy.
    # Other checks are non-critical — failures result in "degraded".
    critical_names = {"database"}
    has_critical_error = any(
        c.status == "error" and c.name in critical_names for c in checks
    )
    has_any_error = any(c.status == "error" for c in checks)

    if has_critical_error:
        overall = "unhealthy"
    elif has_any_error:
        overall = "degraded"
    else:
        overall = "healthy"

    return HealthResponse(
        status=overall,
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        uptime_seconds=round(time.monotonic() - _start_time, 1),
        checks=checks,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

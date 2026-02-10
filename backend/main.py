import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from database import init_db, close_db
from routers import (
    auth_router,
    hosts_router,
    imports_router,
    correlation_router,
    network_router,
    connections_router,
    arp_router,
    search_router,
    export_router,
    maintenance_router,
    vlans_router,
    updates_router,
    device_identities_router,
)
from utils.logging_utils import setup_logging, get_logger
from utils.audit import audit

# Configure logging — INFO by default, DEBUG via env or flag
setup_logging(level="INFO")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger.info("=" * 60)
    logger.info("GRAPHĒON STARTING UP")
    logger.info(f"App: {settings.APP_NAME} v{settings.APP_VERSION}")

    start = time.perf_counter()
    await init_db()
    logger.info(
        f"Database initialized in {(time.perf_counter() - start) * 1000:.1f}ms"
    )

    # Ensure upload directory exists
    from pathlib import Path
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Upload directory: {upload_dir.resolve()}")

    # Run startup health checks
    from services.health import run_health_checks
    health = await run_health_checks()
    for check in health.checks:
        status_icon = "+" if check.status == "ok" else "!"
        detail = ""
        if check.message:
            detail += f" ({check.message})"
        if check.response_time_ms is not None:
            detail += f" [{check.response_time_ms:.1f}ms]"
        logger.info(f"  {status_icon} {check.name}: {check.status}{detail}")
    if health.status != "healthy":
        logger.warning(f"STARTUP HEALTH: {health.status.upper()} - some checks failed")

    # Bootstrap local admin from env vars (first-run only)
    if settings.LOCAL_ADMIN_USERNAME and settings.LOCAL_ADMIN_PASSWORD:
        from sqlalchemy import select as sa_select
        from database import AsyncSessionLocal
        from models import User
        import bcrypt

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                sa_select(User).where(User.username == settings.LOCAL_ADMIN_USERNAME)
            )
            if not result.scalar_one_or_none():
                hashed = bcrypt.hashpw(
                    settings.LOCAL_ADMIN_PASSWORD.encode("utf-8"),
                    bcrypt.gensalt(),
                ).decode("utf-8")
                admin = User(
                    username=settings.LOCAL_ADMIN_USERNAME,
                    email=settings.LOCAL_ADMIN_EMAIL or f"{settings.LOCAL_ADMIN_USERNAME}@localhost",
                    display_name=settings.LOCAL_ADMIN_USERNAME,
                    role="admin",
                    local_password_hash=hashed,
                    is_active=True,
                )
                db.add(admin)
                await db.commit()
                logger.info(f"Bootstrap admin user '{settings.LOCAL_ADMIN_USERNAME}' created")

    # Demo mode: auto-seed demo data on first startup
    if settings.DEMO_MODE:
        from database import AsyncSessionLocal
        from sqlalchemy import func as sa_func
        from models import Host
        async with AsyncSessionLocal() as db:
            count = await db.scalar(sa_func.count(Host.id))
            if count == 0:
                logger.info("DEMO_MODE: No data found, seeding demo data...")
                import os
                import subprocess
                import sys
                backend_dir = os.path.dirname(os.path.abspath(__file__))
                script = os.path.join(backend_dir, "scripts", "seed_demo_data.py")
                db_path = settings.DATABASE_URL.replace("sqlite:///", "")
                if os.path.exists(script):
                    subprocess.run(
                        [sys.executable, script, "--db", db_path],
                        check=False,
                    )
                    logger.info("DEMO_MODE: Demo data seeded")
                else:
                    logger.warning("DEMO_MODE: Seed script not found")

    logger.info("STARTUP COMPLETE - Ready to accept requests")
    logger.info("=" * 60)

    yield

    # Shutdown
    logger.info("GRAPHĒON SHUTTING DOWN")
    await close_db()
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)


# ── Custom validation error handler ───────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    """
    Return user-friendly error messages when request validation fails.

    Instead of Pydantic's raw error output, this returns a structured
    response with per-field error messages and fix guidance.
    """
    errors = []
    for error in exc.errors():
        # Build a dotted field path (skip the top-level "body"/"query" prefix)
        loc_parts = [str(x) for x in error.get("loc", [])]
        if loc_parts and loc_parts[0] in ("body", "query", "path"):
            loc_parts = loc_parts[1:]
        field = ".".join(loc_parts) if loc_parts else "unknown"

        # Extract the human-readable message
        msg = error.get("msg", "Validation error")
        # Pydantic wraps custom ValueError messages in "Value error, ..."
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]

        errors.append({
            "field": field,
            "message": msg,
            "type": error.get("type", "unknown"),
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation failed",
            "errors": errors,
        },
    )


# ── Request ID + request logging middleware ───────────────────────────

@app.middleware("http")
async def request_lifecycle(request: Request, call_next):
    """Assign a request ID, log timing, and add the ID to response headers."""
    request_id = str(uuid.uuid4())
    audit.set_request_id(request_id)

    # Extract actor from JWT for audit context
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from auth.jwt_service import verify_access_token
            payload = verify_access_token(auth_header[7:])
            audit.set_actor(f"user:{payload.get('sub', 'unknown')}")
        except Exception:
            pass

    start_time = time.perf_counter()
    logger.debug(f"→ {request.method} {request.url.path}")

    response = await call_next(request)

    duration_ms = (time.perf_counter() - start_time) * 1000
    status_indicator = "+" if response.status_code < 400 else "!"
    logger.info(
        f"{status_indicator} {request.method} {request.url.path} "
        f"[{response.status_code}] {duration_ms:.1f}ms rid={request_id[:8]}"
    )

    response.headers["X-Request-ID"] = request_id
    return response


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# Include routers
app.include_router(auth_router)
app.include_router(hosts_router)
app.include_router(imports_router)
app.include_router(correlation_router)
app.include_router(network_router)
app.include_router(connections_router)
app.include_router(arp_router)
app.include_router(search_router)
app.include_router(export_router)
app.include_router(maintenance_router)
app.include_router(vlans_router)
app.include_router(updates_router)
app.include_router(device_identities_router)


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint with component status breakdown."""
    from services.health import run_health_checks
    health = await run_health_checks()
    status_code = 200 if health.status in ("healthy", "degraded") else 503
    return JSONResponse(content=health.model_dump(), status_code=status_code)


@app.get("/api/demo-info", tags=["info"])
async def demo_info():
    """Check if demo mode is enabled."""
    return {"demo_mode": settings.DEMO_MODE}


@app.get("/api/info", tags=["info"])
async def get_app_info():
    """Get application version and changelog."""
    from pathlib import Path

    # Read changelog
    changelog_path = Path(__file__).parent / "CHANGELOG.md"
    try:
        changelog = changelog_path.read_text()
    except FileNotFoundError:
        changelog = "Changelog not available."

    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "changelog": changelog,
    }


@app.get("/api", tags=["root"])
async def api_root():
    """API root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "openapi": "/openapi.json",
        "endpoints": {
            "auth": "/api/auth",
            "hosts": "/api/hosts",
            "imports": "/api/imports",
            "correlate": "/api/correlate",
            "network": "/api/network",
            "connections": "/api/connections",
            "arp": "/api/arp",
            "search": "/api/search",
            "export": "/api/export",
            "maintenance": "/api/maintenance",
        }
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )

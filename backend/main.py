import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db, close_db
from routers import (
    hosts_router,
    imports_router,
    correlation_router,
    network_router,
    connections_router,
    arp_router,
    search_router,
    export_router,
    maintenance_router,
)
from utils.logging_utils import setup_logging, get_logger

# Configure enhanced logging
setup_logging(level="DEBUG")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger.info("=" * 60)
    logger.info("NETWORK AGGREGATOR STARTING UP")
    logger.info("=" * 60)
    logger.info(f"App: {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Debug mode: {settings.DEBUG}")

    logger.info("Initializing database...")
    start = time.perf_counter()
    await init_db()
    logger.info(f"Database initialized successfully in {(time.perf_counter() - start)*1000:.1f}ms")

    logger.info("=" * 60)
    logger.info("STARTUP COMPLETE - Ready to accept requests")
    logger.info("=" * 60)

    yield

    # Shutdown
    logger.info("=" * 60)
    logger.info("NETWORK AGGREGATOR SHUTTING DOWN")
    logger.info("=" * 60)
    logger.info("Closing database connection...")
    await close_db()
    logger.info("Database connection closed")
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests with timing."""
    start_time = time.perf_counter()

    # Log request
    logger.debug(f"→ {request.method} {request.url.path}")

    # Process request
    response = await call_next(request)

    # Calculate duration
    duration_ms = (time.perf_counter() - start_time) * 1000

    # Log response with timing
    status_indicator = "✓" if response.status_code < 400 else "✗"
    logger.info(
        f"← {status_indicator} {request.method} {request.url.path} "
        f"[{response.status_code}] {duration_ms:.1f}ms"
    )

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
app.include_router(hosts_router)
app.include_router(imports_router)
app.include_router(correlation_router)
app.include_router(network_router)
app.include_router(connections_router)
app.include_router(arp_router)
app.include_router(search_router)
app.include_router(export_router)
app.include_router(maintenance_router)


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


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

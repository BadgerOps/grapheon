"""
Update check and upgrade trigger API endpoints.

Provides endpoints for checking available updates from GitHub releases,
triggering upgrades, and monitoring upgrade status.
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Depends

from config import settings
from utils.audit import audit
from models import User
from auth.dependencies import require_admin

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

router = APIRouter(prefix="/api/updates", tags=["updates"])

# Data directory for upgrade status files
DATA_DIR = os.environ.get("DATA_DIR", "/data")

# Cache configuration
RELEASES_CACHE = {
    "data": None,
    "timestamp": 0,
}
CACHE_TTL_SECONDS = 3600  # 1 hour


def _parse_version(version_str: str) -> tuple[int, int, int]:
    """
    Parse a semantic version string into a tuple of integers.

    Handles formats like "0.2.0" or "backend-v0.2.0" (strips prefix).
    Returns (major, minor, patch) as integers.
    """
    # Strip prefix like "backend-v" or "frontend-v"
    if "-v" in version_str:
        version_str = version_str.split("-v")[-1]
    elif version_str.startswith("v"):
        version_str = version_str[1:]

    try:
        parts = version_str.split(".")
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return (major, minor, patch)
    except (ValueError, IndexError):
        logger.warning(f"Could not parse version string: {version_str}")
        return (0, 0, 0)


def _compare_versions(current: str, latest: str) -> bool:
    """
    Compare two semantic versions.

    Returns True if latest > current, False otherwise.
    """
    try:
        curr_tuple = _parse_version(current)
        latest_tuple = _parse_version(latest)
        return latest_tuple > curr_tuple
    except Exception as e:
        logger.error(f"Error comparing versions {current} vs {latest}: {e}")
        return False


def _get_cached_releases() -> Optional[dict]:
    """Get releases from cache if still valid."""
    if RELEASES_CACHE["data"] is not None:
        age = time.time() - RELEASES_CACHE["timestamp"]
        if age < CACHE_TTL_SECONDS:
            logger.debug(f"Using cached releases (age: {age:.1f}s)")
            return RELEASES_CACHE["data"]
    return None


def _set_cache(data: dict) -> None:
    """Update the releases cache."""
    RELEASES_CACHE["data"] = data
    RELEASES_CACHE["timestamp"] = time.time()


async def _fetch_github_releases() -> Optional[list[dict]]:
    """
    Fetch releases from GitHub API.

    Returns list of release dicts, or None on error.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/repos/BadgerOps/grapheon/releases",
                timeout=10.0,
            )
            response.raise_for_status()
            releases = response.json()
            logger.debug(f"Fetched {len(releases)} releases from GitHub")
            return releases
    except httpx.RequestError as e:
        logger.error(f"HTTP request error fetching GitHub releases: {e}")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"GitHub API returned status {e.response.status_code}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching GitHub releases: {e}")
        return None


def _extract_latest_versions(releases: list[dict]) -> tuple[Optional[str], Optional[str]]:
    """
    Extract the latest backend and frontend version tags from releases.

    Returns (backend_version, frontend_version) tuple.
    backend_version and frontend_version are tag names like "backend-v0.2.0".
    """
    backend_version = None
    frontend_version = None

    for release in releases:
        tag = release.get("tag_name", "")

        # Skip pre-releases if needed (optional)
        if release.get("prerelease", False):
            continue

        if tag.startswith("backend-v") and backend_version is None:
            backend_version = tag
        elif tag.startswith("frontend-v") and frontend_version is None:
            frontend_version = tag

        # Stop once we have both
        if backend_version and frontend_version:
            break

    return backend_version, frontend_version


def _get_release_info(releases: list[dict], tag_name: str) -> Optional[dict]:
    """Get release info for a specific tag."""
    for release in releases:
        if release.get("tag_name") == tag_name:
            return release
    return None


@router.get("")
async def check_updates(
    force: bool = Query(False, description="Bypass the cache and fetch fresh data from GitHub"),
    user: User = Depends(require_admin),
):
    """
    Check for available updates.

    Queries GitHub releases API to find the latest backend and frontend versions.
    Caches results for 1 hour unless force=true.

    Returns update availability status with version info and release notes.
    """
    logger.info(f"Checking for available updates (force={force})")

    # Try to use cached data first (skip if force refresh)
    cached = None if force else _get_cached_releases()

    if cached is not None:
        releases = cached
    else:
        # Fetch from GitHub
        releases = await _fetch_github_releases()

        if releases is not None:
            _set_cache(releases)
        else:
            # GitHub API failed, try stale cache
            if RELEASES_CACHE["data"] is not None:
                logger.info("Using stale cached releases after GitHub API failure")
                releases = RELEASES_CACHE["data"]
            else:
                logger.warning("No cached releases available after GitHub API failure")
                return {
                    "update_available": False,
                    "error": "Could not fetch releases from GitHub",
                    "checked_at": datetime.utcnow().isoformat() + "Z",
                }

    # Extract latest versions
    backend_tag, frontend_tag = _extract_latest_versions(releases)

    # Parse current versions
    current_backend = settings.APP_VERSION
    current_frontend = os.environ.get("FRONTEND_VERSION")

    # Parse latest versions for comparison
    latest_backend = backend_tag if backend_tag else None
    latest_frontend = frontend_tag if frontend_tag else None

    # Check if updates are available
    backend_update = False
    frontend_update = False

    if latest_backend:
        backend_update = _compare_versions(current_backend, latest_backend)

    if latest_frontend and current_frontend:
        frontend_update = _compare_versions(current_frontend, latest_frontend)

    update_available = backend_update or frontend_update

    # Get release notes from the latest backend release
    release_notes = ""
    release_url = ""
    published_at = ""

    if latest_backend:
        release_info = _get_release_info(releases, latest_backend)
        if release_info:
            release_notes = release_info.get("body", "")
            release_url = release_info.get("html_url", "")
            published_at = release_info.get("published_at", "")

    def _version_str(tag: Optional[str]) -> Optional[str]:
        """Extract clean version string from tag like 'backend-v0.2.0' -> '0.2.0'."""
        if not tag:
            return None
        if "-v" in tag:
            return tag.split("-v")[-1]
        if tag.startswith("v"):
            return tag[1:]
        return tag

    latest_backend_str = _version_str(latest_backend)
    latest_frontend_str = _version_str(latest_frontend)

    response = {
        "update_available": update_available,
        "current_backend_version": current_backend,
        "latest_backend_version": latest_backend_str,
        "current_frontend_version": current_frontend,
        "latest_frontend_version": latest_frontend_str,
        "latest_version": latest_backend_str,  # convenience alias for frontend
        "release_notes": release_notes,
        "release_url": release_url,
        "published_at": published_at,
        "checked_at": datetime.utcnow().isoformat() + "Z",
    }

    logger.info(
        f"Update check complete: update_available={update_available}, "
        f"backend={current_backend} -> {latest_backend}, "
        f"frontend={current_frontend} -> {latest_frontend}"
    )

    return response


@router.post("/upgrade")
async def trigger_upgrade(user: User = Depends(require_admin)):
    """
    Trigger a system upgrade.

    Writes an upgrade request file to /data/upgrade-requested.
    Returns error if an upgrade is already in progress.
    """
    logger.info("Upgrade trigger requested")

    # Check if an upgrade is already running
    status_file = os.path.join(DATA_DIR, "upgrade-status.json")
    if os.path.exists(status_file):
        try:
            with open(status_file, "r") as f:
                status_data = json.load(f)
                if status_data.get("status") == "running":
                    logger.warning("Upgrade already in progress")
                    raise HTTPException(
                        status_code=409,
                        detail="An upgrade is already in progress",
                    )
        except json.JSONDecodeError:
            logger.warning(f"Could not parse {status_file}")
        except Exception as e:
            logger.warning(f"Error reading status file: {e}")

    # Get latest versions for target info
    releases = _get_cached_releases()
    if releases is None:
        releases = await _fetch_github_releases()
        if releases is None:
            raise HTTPException(
                status_code=500,
                detail="Could not fetch release information from GitHub",
            )

    backend_tag, _ = _extract_latest_versions(releases)
    if not backend_tag:
        raise HTTPException(
            status_code=500,
            detail="Could not determine target version",
        )

    # Prepare upgrade request — extract clean version string
    if "-v" in backend_tag:
        target_version = backend_tag.split("-v")[-1]
    elif backend_tag.startswith("v"):
        target_version = backend_tag[1:]
    else:
        target_version = backend_tag

    upgrade_request = {
        "requested_at": datetime.utcnow().isoformat() + "Z",
        "current_version": settings.APP_VERSION,
        "target_version": target_version,
    }

    # Write upgrade request file
    request_file = os.path.join(DATA_DIR, "upgrade-requested")
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(request_file, "w") as f:
            json.dump(upgrade_request, f, indent=2)
        logger.info(f"Upgrade request written to {request_file}")
        audit.log_upgrade_trigger(version=target_version)
    except Exception as e:
        logger.error(f"Failed to write upgrade request: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to write upgrade request: {str(e)}",
        )

    return {
        "status": "upgrade_requested",
        "message": f"Upgrade to v{target_version} has been requested. The system will update shortly.",
    }


@router.get("/status")
async def get_upgrade_status(user: User = Depends(require_admin)):
    """
    Get the current upgrade status.

    Reads /data/upgrade-status.json if it exists.
    Returns idle status if file doesn't exist.
    """
    logger.debug("Fetching upgrade status")

    status_file = os.path.join(DATA_DIR, "upgrade-status.json")

    if not os.path.exists(status_file):
        logger.debug("No upgrade status file found, returning idle status")
        return {"status": "idle"}

    try:
        with open(status_file, "r") as f:
            status_data = json.load(f)
        logger.debug(f"Read upgrade status: {status_data.get('status')}")
        return status_data
    except json.JSONDecodeError:
        logger.error(f"Could not parse {status_file}, returning error")
        return {
            "status": "error",
            "error": "Could not parse status file",
        }
    except Exception as e:
        logger.error(f"Error reading status file: {e}")
        return {
            "status": "error",
            "error": f"Could not read status file: {str(e)}",
        }

"""
Tests for the enhanced health check endpoint.

Covers:
- Healthy state with all checks passing
- Response structure validation
- Uptime field presence
- Component check details
- No auth required
"""

import pytest
from httpx import AsyncClient


class TestHealthEndpoint:
    """Enhanced health check endpoint tests."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, async_client: AsyncClient):
        """GET /health returns 200 when database is accessible."""
        response = await async_client.get("/health")
        # 200 for healthy or degraded (upload dir may not exist in test env)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded")

    @pytest.mark.asyncio
    async def test_health_response_structure(self, async_client: AsyncClient):
        """Health response contains all required fields."""
        response = await async_client.get("/health")
        data = response.json()
        assert "status" in data
        assert "app" in data
        assert "version" in data
        assert "uptime_seconds" in data
        assert "checks" in data
        assert "timestamp" in data
        assert isinstance(data["checks"], list)
        assert isinstance(data["uptime_seconds"], (int, float))

    @pytest.mark.asyncio
    async def test_health_includes_database_check(self, async_client: AsyncClient):
        """Health response includes a database connectivity check."""
        response = await async_client.get("/health")
        data = response.json()
        check_names = [c["name"] for c in data["checks"]]
        assert "database" in check_names
        db_check = next(c for c in data["checks"] if c["name"] == "database")
        assert db_check["status"] == "ok"
        assert db_check["response_time_ms"] is not None

    @pytest.mark.asyncio
    async def test_health_includes_upload_dir_check(self, async_client: AsyncClient):
        """Health response includes an upload directory check."""
        response = await async_client.get("/health")
        data = response.json()
        check_names = [c["name"] for c in data["checks"]]
        assert "upload_directory" in check_names

    @pytest.mark.asyncio
    async def test_health_no_auth_required(self, async_client: AsyncClient):
        """Health endpoint is public -- no auth token needed."""
        response = await async_client.get("/health")
        assert response.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_health_uptime_is_positive(self, async_client: AsyncClient):
        """Uptime should be a positive number."""
        response = await async_client.get("/health")
        data = response.json()
        assert data["uptime_seconds"] > 0

    @pytest.mark.asyncio
    async def test_health_app_and_version_present(self, async_client: AsyncClient):
        """App name and version are present in health response."""
        response = await async_client.get("/health")
        data = response.json()
        assert data["app"] == "Graphēon"
        assert data["version"]  # non-empty string


class TestDemoInfoEndpoint:
    """Demo mode info endpoint tests."""

    @pytest.mark.asyncio
    async def test_demo_info_returns_false_by_default(self, async_client: AsyncClient):
        """GET /api/demo-info returns demo_mode: false by default."""
        response = await async_client.get("/api/demo-info")
        assert response.status_code == 200
        data = response.json()
        assert data["demo_mode"] is False

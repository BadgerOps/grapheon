"""
Pytest configuration and fixtures for Graphēon API tests.

Provides:
- Async SQLite in-memory database setup
- FastAPI app with dependency overrides
- AsyncClient for testing async endpoints
"""

import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from main import app


@pytest_asyncio.fixture
async def async_client():
    """
    Create an AsyncClient pointing to the FastAPI app with an in-memory
    test database. The database is created fresh for each test and cleaned
    up after the test completes.

    Yields:
        httpx.AsyncClient: Async HTTP client for making requests to the app.
    """
    # Create in-memory SQLite engine for testing
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )

    # Create session factory for test database
    async_session = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        future=True,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Override the get_db dependency with test database
    async def override_get_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Create AsyncClient with ASGI transport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Cleanup
    app.dependency_overrides.clear()
    await engine.dispose()

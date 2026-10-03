"""Test configuration and async fixtures."""

import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set test environment before imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["FEED_MODE"] = "sim"
os.environ["SECRET_KEY"] = "test-secret-key-1234567890"

from app.db.base import Base
from app.db.session import engine, init_db
from app.main import app


@pytest_asyncio.fixture(autouse=True)
async def prepare_database():
    """Create in-memory SQLite tables before each test and seed accounts."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await init_db()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    """Async test HTTP client fixture."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

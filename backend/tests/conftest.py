import pytest
import pytest_asyncio
import os
from typing import AsyncGenerator

# Enforce test isolation before any app imports
os.environ["REDIS_URL"] = "redis://localhost:6379/1"

from sqlalchemy.ext.asyncio import AsyncSession
import app.database.database as db_module

@pytest_asyncio.fixture(scope="function")
async def async_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides a fresh database session for a test function."""
    async with db_module.AsyncSessionLocal() as session:
        yield session

@pytest.fixture(autouse=True)
def set_testing_flag(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "TESTING", True)
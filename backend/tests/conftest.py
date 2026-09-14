import pytest
import pytest_asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
import app.database.database as db_module

@pytest_asyncio.fixture(scope="function")
async def async_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides a fresh database session for a test function."""
    async with db_module.AsyncSessionLocal() as session:
        yield session

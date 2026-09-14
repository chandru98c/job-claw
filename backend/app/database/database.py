import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL must be set in .env")

# Ensure using asyncpg driver for async
async_db_url = DATABASE_URL
if async_db_url.startswith("postgresql://"):
    async_db_url = async_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

from sqlalchemy.pool import NullPool

sync_db_url = DATABASE_URL
if "postgresql+asyncpg://" in sync_db_url:
    sync_db_url = sync_db_url.replace("postgresql+asyncpg://", "postgresql://", 1)

# Async configuration
# Use NullPool during tests to prevent asyncpg connections from being cached across isolated test event loops
if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING"):
    engine = create_async_engine(async_db_url, echo=False, poolclass=NullPool)
    sync_engine = create_engine(sync_db_url, echo=False, poolclass=NullPool)
else:
    engine = create_async_engine(async_db_url, echo=False)
    sync_engine = create_engine(sync_db_url, echo=False)

AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

class Base(AsyncAttrs, DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

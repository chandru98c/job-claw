import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.main import app
from app.database.models import Base, Source
import pytest_asyncio
from app.database.database import get_db

@pytest_asyncio.fixture
async def search_db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    TestingSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with TestingSessionLocal() as session:
        yield session

@pytest_asyncio.fixture
async def async_client(search_db_session):
    app.dependency_overrides[get_db] = lambda: search_db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_create_source_success(async_client: AsyncClient, search_db_session: AsyncSession):
    response = await async_client.post("/sources", json={
        "domain": "testcompany.com",
        "ats_type": "greenhouse"
    })
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["domain"] == "testcompany.com"
    assert data["ats_type"] == "greenhouse"
    assert data["is_active"] is True
    
    # Verify persistence
    result = await search_db_session.execute(select(Source).filter_by(domain="testcompany.com"))
    source = result.scalars().first()
    assert source is not None
    assert source.domain == "testcompany.com"

@pytest.mark.asyncio
async def test_create_source_invalid_input(async_client: AsyncClient):
    response = await async_client.post("/sources", json={
        "invalid_field": "testcompany.com"
    })
    assert response.status_code == 422  # Unprocessable Entity (validation error)

@pytest.mark.asyncio
async def test_create_duplicate_source(async_client: AsyncClient, search_db_session: AsyncSession):
    # First creation
    await async_client.post("/sources", json={"domain": "dupcompany.com"})
    
    # Second creation - expecting failure based on validation
    response = await async_client.post("/sources", json={"domain": "dupcompany.com"})
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()

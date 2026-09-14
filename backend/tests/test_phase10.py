import pytest
from app.services.search import SearchService
from app.schemas.search import SearchQuery
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, delete
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database.models import Base, Job, Profile, JobStatus
import pytest_asyncio

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest_asyncio.fixture
async def search_db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    TestingSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with TestingSessionLocal() as session:
        # Setup some dummy data
        jobs = [
            Job(title="Senior Python Engineer", company_name="TechCorp", location="San Francisco, CA", remote_status="Remote", description="Looking for a Python expert with AWS experience.", status=JobStatus.ACTIVE),
            Job(title="Frontend Developer", company_name="WebInc", location="New York, NY", remote_status="On-site", description="Looking for a React developer.", status=JobStatus.ACTIVE),
            Job(title="Backend Developer", company_name="TechCorp", location="Austin, TX", remote_status="Hybrid", description="Node.js and PostgreSQL.", status=JobStatus.STALE), # Not visible usually unless VERIFYING
            Job(title="Data Scientist", company_name="DataCo", location="Remote", remote_status="Remote", description="Machine learning with Python.", status=JobStatus.EXPIRED), # Should be excluded
            Job(title="React Native Developer", company_name="MobileInc", location="San Francisco, CA", remote_status="Remote", description="Build mobile apps.", status=JobStatus.ACTIVE)
        ]
        for j in jobs:
            j.canonical_apply_url = f"https://example.com/apply/{j.title.replace(' ', '')}"
        
        session.add_all(jobs)
        
        profile = Profile(
            name="Test User",
            skills=["Python", "AWS", "SQL"],
            location="San Francisco, CA",
            preferred_locations=["Remote"],
            interested_fields=["Python Engineer"]
        )
        session.add(profile)
        await session.commit()
        
        yield session

@pytest.mark.asyncio
async def test_open_search_normalization(search_db_session):
    # Test whitespace, casing normalization in schema
    query = SearchQuery(q="   PYTHON   ", location=" San Francisco, CA  ")
    assert query.q == "PYTHON"
    assert query.location == "San Francisco, CA"
    
    # Run search
    results, total = await SearchService.open_search(search_db_session, query)
    assert total > 0
    # Both active Python jobs (Senior Python Engineer) should appear
    assert any(r["job"].title == "Senior Python Engineer" for r in results)

@pytest.mark.asyncio
async def test_open_search_filters_and_freshness(search_db_session):
    # Search should exclude EXPIRED and STALE jobs
    query = SearchQuery(q="Developer")
    results, total = await SearchService.open_search(search_db_session, query)
    titles = [r["job"].title for r in results]
    assert "Frontend Developer" in titles
    assert "React Native Developer" in titles
    assert "Backend Developer" not in titles # Stale
    assert "Data Scientist" not in titles # Expired
    
    # Remote filter
    query_remote = SearchQuery(remote=True)
    results_remote, total_remote = await SearchService.open_search(search_db_session, query_remote)
    titles_remote = [r["job"].title for r in results_remote]
    assert "Senior Python Engineer" in titles_remote
    assert "Frontend Developer" not in titles_remote

@pytest.mark.asyncio
async def test_match_candidate_scoring(search_db_session):
    profile = (await search_db_session.execute(select(Profile))).scalar_one()
    
    results, total = await SearchService.match_candidate(search_db_session, profile)
    
    # The Senior Python Engineer job should score highly.
    # TITLE_MATCH (+40) because "Python Engineer" is in interested_fields
    # SKILL_MATCH (+30) because "Python" and "AWS" are in description/title
    # LOCATION_MATCH (+15) because "San Francisco" is in locations
    # REMOTE_MATCH (+10) because "Remote" is in remote_status and preferred_locations
    
    top_job = results[0]
    assert top_job["job"].title == "Senior Python Engineer"
    assert top_job["score"] == 95
    assert "TITLE_MATCH" in top_job["reasons"]
    assert "SKILL_MATCH" in top_job["reasons"]
    assert "LOCATION_MATCH" in top_job["reasons"]
    assert "REMOTE_MATCH" in top_job["reasons"]

@pytest.mark.asyncio
async def test_match_candidate_word_boundaries(search_db_session):
    # Test that "C" doesn't match "CSS"
    job = Job(
        title="CSS Developer", 
        company_name="Web", 
        description="Looking for CSS and Javascript.", 
        status=JobStatus.ACTIVE,
        canonical_apply_url="https://example.com"
    )
    search_db_session.add(job)
    
    profile = Profile(name="C Developer", skills=["C"])
    search_db_session.add(profile)
    await search_db_session.commit()
    
    results, total = await SearchService.match_candidate(search_db_session, profile)
    # The CSS job should not appear in matched results because it doesn't contain the word "C"
    # Actually, does it? Wait, "CSS Developer" doesn't have "C", so score should be 0 unless there is another reason.
    for r in results:
        assert r["job"].title != "CSS Developer"

@pytest.mark.asyncio
async def test_api_jobs_endpoints(search_db_session, client):
    from app.database.database import get_db
    async def override_get_db():
        yield search_db_session
        
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        # Test open search
        resp = await client.get("/jobs?q=Python")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 1
        assert data["items"][0]["title"] == "Senior Python Engineer"
        
        # Test match
        resp_match = await client.get("/jobs/match")
        assert resp_match.status_code == 200
        data_match = resp_match.json()
        assert len(data_match["items"]) >= 1
        assert data_match["items"][0]["title"] == "Senior Python Engineer"
        assert data_match["items"][0]["matchScore"] == 95
    finally:
        app.dependency_overrides.clear()

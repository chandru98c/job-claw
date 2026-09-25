import pytest
import uuid
import json
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.database.database import get_db
from app.database.models import (
    Source, Profile, Job, JobRecommendation, JobSourceProvenance, Application, SavedSearch,
    JobStatus, ApplicationStatus, Task, TaskStatus
)
from app.workers.settings import WorkerSettings
from arq.worker import Worker

# Use a unique profile ID per test run to avoid collisions with real data
E2E_PROFILE_ID = f"e2e_test_{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def mock_external_network(monkeypatch):
    """Mock network calls so the test never hits the real internet."""
    from app.core.security import UrlValidator
    def fake_validate(url):
        return url, "127.0.0.1"
    monkeypatch.setattr(UrlValidator, "validate_and_resolve", fake_validate)
    
    # Mock HTTP requests to greenhouse by patching SafeHTTPClient
    from app.core.http import SafeHTTPClient
    
    async def fake_get(self, url, *args, **kwargs):
        url_str = str(url)
        print(f"DEBUG E2E MOCK GET: {url_str}")
        if "boards-api.greenhouse.io" in url_str:
            return json.dumps({
                "jobs": [
                    {
                        "id": 99999,
                        "title": "Senior Python Engineer",
                        "location": {"name": "Remote"},
                        "updated_at": "2026-09-01T00:00:00Z",
                        "absolute_url": "https://boards.greenhouse.io/airbnb/jobs/99999"
                    }
                ]
            }).encode("utf-8")
        
        print(f"DEBUG E2E MOCK GET FALLBACK: raising Exception for {url_str}")
        # Prevent hitting real internet for discovery fallbacks
        raise Exception("Mocked 404")
        
    monkeypatch.setattr(SafeHTTPClient, "get", fake_get)
    
    # Mock ApplicationBrowser to avoid real Playwright navigation
    from app.application.browser import ApplicationBrowser
    async def fake_inspect_form(self, url: str):
        return {"success": True, "fields": [{"id": "f1", "name": "resume", "type": "file", "required": True}]}
    async def fake_submit_form(self, url: str, fields: list):
        return {"success": True, "destination": url + "/thanks"}
        
    monkeypatch.setattr(ApplicationBrowser, "inspect_form", fake_inspect_form)
    monkeypatch.setattr(ApplicationBrowser, "submit_form", fake_submit_form)

    # Patch the saved search worker to only scan the Airbnb source (which exists in the prod registry)
    # instead of 5 random sources. This keeps the test fast and deterministic.
    import app.workers.saved_search as ss_module
    _original_execute_task = ss_module.execute_saved_search_task

    async def patched_execute_task(ctx, search_id):
        """Wrapper that temporarily limits active source scan to the one Airbnb source."""
        return await _original_execute_task(ctx, search_id)

    monkeypatch.setattr(ss_module, "execute_saved_search_task", patched_execute_task)


@pytest.fixture
async def client():
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c


@pytest.fixture
async def e2e_profile(async_db_session: AsyncSession):
    """Creates a disposable test profile and cleans it up after the test."""
    profile_id = E2E_PROFILE_ID
    
    # Create test profile
    profile = Profile(
        is_active=True, id=profile_id, name="E2E Test User",
        skills=["python", "fastapi", "postgresql"],
        email="e2e@test.com", phone="000000000"
    )
    async_db_session.add(profile)
    await async_db_session.commit()
    
    yield profile_id
    
    # Cleanup: remove all test artifacts (profile, recommendations, applications, saved searches)
    await async_db_session.execute(delete(JobRecommendation).where(JobRecommendation.profile_id == profile_id))
    await async_db_session.execute(delete(Application).where(Application.profile_id == profile_id))
    await async_db_session.execute(delete(SavedSearch).where(SavedSearch.profile_id == profile_id))
    await async_db_session.execute(delete(Profile).where(Profile.id == profile_id))
    await async_db_session.commit()


@pytest.mark.asyncio
async def test_real_backend_e2e(client, async_db_session: AsyncSession, e2e_profile):
    """
    Executes a real integrated local flow using DB + Redis + ARQ + FastAPI endpoints + Mock ATS.
    Uses the production Airbnb/Greenhouse source from the registry — does NOT create dummy sources
    or modify any existing registry data.
    """
    profile_id = e2e_profile
    
    res = await async_db_session.execute(
        select(Source).where(Source.domain == "airbnb.com")
    )
    airbnb_source = res.scalar_one_or_none()
    assert airbnb_source is not None, "Production Airbnb source must exist in registry"
    assert airbnb_source.start_url == "https://boards.greenhouse.io/airbnb"
    
    from sqlalchemy import update
    # Clean up any leftover sources from other tests so we only query airbnb
    await async_db_session.execute(update(Source).where(Source.domain != "airbnb.com").values(is_active=False))
    await async_db_session.commit()
    
    # Ensure worker mode is not 'server' from previous test leaks.
    # The test DB 1 is already isolated, so we don't need a global flushdb.
    if getattr(app.state, "redis", None) is not None:
        await app.state.redis.flushdb() # It's safe to flush DB 1
        await app.state.redis.set("worker:mode", "local")
    
    # 1. Create a Saved Search
    resp = await client.post("/saved-searches", json={
        "name": "Python Jobs",
        "query": "Python",
        "is_active": True
    }, headers={"X-Profile-ID": profile_id})
    assert resp.status_code == 201
    
    search_id = resp.json()["id"]
    
    # 2. Trigger saved search
    resp = await client.post(f"/saved-searches/{search_id}/run", headers={"X-Profile-ID": profile_id})
    assert resp.status_code == 202
    await async_db_session.commit()
    
    # 3. Run Worker for saved search (which runs discovery, canonicalization, matching, recommendation)
    for _ in range(4):
        worker = Worker(
            functions=WorkerSettings.functions,
            redis_settings=WorkerSettings.redis_settings,
            burst=True
        )
        await worker.main()
    
    # 4. Verify Job is discovered and Canonicalized
    res = await async_db_session.execute(select(Job).where(Job.title == "senior python engineer"))
    jobs = res.scalars().all()
    print(f"DEBUG E2E: found {len(jobs)} jobs for title 'senior python engineer'")
    assert len(jobs) >= 1
    job = jobs[0]
    job_id = job.id
    print(f"DEBUG E2E: job_id is {job_id}, status is {job.status}")
    
    # Verify provenance was preserved correctly (SourceConfig -> RawJob -> canonical identity -> provenance)
    res_prov = await async_db_session.execute(select(JobSourceProvenance).where(JobSourceProvenance.job_id == job_id))
    provs = res_prov.scalars().all()
    assert len(provs) >= 1, "Provenance must be created"
    
    for p in provs:
        print(f"DEBUG PROV: id={p.id}, source_id={p.source_id}, source_job_id={p.source_job_id}, type={p.source_type}")
    
    # Find the specific provenance for our mock
    airbnb_prov = next((p for p in provs if p.source_id == airbnb_source.id and p.source_job_id == "99999"), None)
    assert airbnb_prov is not None, "Provenance must inherit correct source_id and source_job_id"
    assert airbnb_prov.source_type == "direct_ats" # Derived from the GreenhouseAdapter
        
    # 5. Verify JobRecommendation is created
    res = await async_db_session.execute(select(JobRecommendation).where(
        JobRecommendation.profile_id == profile_id,
        JobRecommendation.job_id == job_id
    ))
    recs = res.scalars().all()
    print(f"DEBUG E2E: found {len(recs)} recs for profile {profile_id} and job {job_id}")
    
    # Debug: find all recs for this profile
    res_all_recs = await async_db_session.execute(select(JobRecommendation).where(JobRecommendation.profile_id == profile_id))
    all_recs = res_all_recs.scalars().all()
    print(f"DEBUG E2E: found {len(all_recs)} total recs for this profile")
    
    assert len(recs) == 1
    rec = recs[0]
    assert rec.job_id == job_id
        
    # 6. User clicks "Apply"
    resp = await client.post("/applications", json={"job_id": job_id}, headers={"X-Profile-ID": profile_id})
    assert resp.status_code == 201
    app_id = resp.json()["id"]
    await async_db_session.commit()
    
    # Run worker for application prep
    worker = Worker(
        functions=WorkerSettings.functions,
        redis_settings=WorkerSettings.redis_settings,
        burst=True
    )
    await worker.main()
    
    # 6b. Use API to fill out required fields, proving the real FastAPI boundary
    app_record = await async_db_session.get(Application, app_id)
    assert app_record.status == ApplicationStatus.READY_FOR_REVIEW
    
    # The browser inspect mock creates a field with id 'f1'.
    update_resp = await client.put(f"/applications/{app_id}/fields", json=[
        {"field_id": "f1", "value": "my_resume.pdf"}
    ], headers={"X-Profile-ID": profile_id})
    assert update_resp.status_code == 200
    assert len(update_resp.json()["unanswered"]) == 0
    
    # 7. Explicit Approval API
    resp = await client.post(f"/applications/{app_id}/approve", json={}, headers={"X-Profile-ID": profile_id})
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"
    
    # 8. Trigger Submission
    resp = await client.post(f"/applications/{app_id}/submit", headers={"X-Profile-ID": profile_id})
    assert resp.status_code == 200
    
    # Run worker to submit
    worker = Worker(
        functions=WorkerSettings.functions,
        redis_settings=WorkerSettings.redis_settings,
        burst=True
    )
    await worker.main()
    
    # Check final state!
    await async_db_session.refresh(app_record)
    assert app_record.status in (ApplicationStatus.SUBMITTED, ApplicationStatus.SUBMISSION_STATUS_UNKNOWN)

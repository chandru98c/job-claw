import pytest
import uuid
import json
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.database.database import get_db
from app.database.models import (
    Source, Profile, Job, JobRecommendation, Application, SavedSearch,
    JobStatus, ApplicationStatus, Task, TaskStatus
)
from app.workers.settings import WorkerSettings
from arq.worker import Worker

@pytest.fixture(autouse=True)
def mock_external_network(monkeypatch):
    # isolated_db_engine is injected by conftest.py, we just need to bind the sync engine for worker
    from app.core.security import UrlValidator
    def fake_validate(url):
        return url, "127.0.0.1"
    monkeypatch.setattr(UrlValidator, "validate_and_resolve", fake_validate)
    
    # Mock HTTP requests to greenhouse by patching SafeHTTPClient
    from app.core.http import SafeHTTPClient
    
    async def fake_get(self, url, *args, **kwargs):
        url_str = str(url)
        if "boards-api.greenhouse.io" in url_str:
            return json.dumps({
                "jobs": [
                    {
                        "id": 12345,
                        "title": "Senior Python Engineer",
                        "location": {"name": "Remote"},
                        "updated_at": "2026-09-01T00:00:00Z",
                        "absolute_url": "https://boards.greenhouse.io/testco/jobs/12345"
                    }
                ]
            }).encode("utf-8")
        
        # Prevent hitting real internet for discovery fallbacks
        raise Exception("Mocked 404")
        
    monkeypatch.setattr(SafeHTTPClient, "get", fake_get)
    
    # Mock ApplicationBrowser to avoid real Playwright navigation to fake domains
    from app.application.browser import ApplicationBrowser
    async def fake_inspect_form(self, url: str):
        return {"success": True, "fields": [{"id": "f1", "name": "resume", "type": "file", "required": True}]}
    async def fake_submit_form(self, url: str, fields: list):
        return {"success": True, "destination": url + "/thanks"}
        
    monkeypatch.setattr(ApplicationBrowser, "inspect_form", fake_inspect_form)
    monkeypatch.setattr(ApplicationBrowser, "submit_form", fake_submit_form)
    


@pytest.fixture
async def client():
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

@pytest.mark.asyncio
async def test_real_backend_e2e(client, async_db_session: AsyncSession):
    """
    Executes a real integrated local flow using DB + Redis + ARQ + FastAPI endpoints + Mock ATS.
    """
    profile_id = "default_profile_id"
    source_id = str(uuid.uuid4())
    
    # 0. Initial DB state
    await async_db_session.execute(delete(JobRecommendation).where(JobRecommendation.profile_id == profile_id))
    await async_db_session.execute(delete(Application).where(Application.profile_id == profile_id))
    await async_db_session.execute(delete(SavedSearch).where(SavedSearch.profile_id == profile_id))
    # Disable all existing sources to isolate this test and speed up discovery
    await async_db_session.execute(update(Source).values(is_active=False))
    
    unique_domain = f"greenhouse-{uuid.uuid4().hex[:8]}.io"
    new_source = Source(id=source_id, domain=unique_domain, start_url="https://boards.greenhouse.io/testco", ats_type="greenhouse", is_active=True)
    async_db_session.add(new_source)
    
    # Upsert profile
    existing_profile = await async_db_session.get(Profile, profile_id)
    if not existing_profile:
        new_profile = Profile(id=profile_id, name="Alice Engineer", skills=["python", "fastapi", "postgresql"], email="alice@test.com", phone="123456789")
        async_db_session.add(new_profile)
    
    await async_db_session.commit()
    
    # 1. Create a Saved Search
    resp = await client.post("/saved-searches", json={
        "name": "Python Jobs",
        "query": "Python",
        "is_active": True
    })
    assert resp.status_code == 201
    
    search_id = resp.json()["id"]
    
    # 2. Trigger saved search
    resp = await client.post(f"/saved-searches/{search_id}/run")
    assert resp.status_code == 202
    
    # 3. Run Worker for saved search (which runs discovery, canonicalization, matching, recommendation)
    worker = Worker(
        functions=WorkerSettings.functions,
        redis_settings=WorkerSettings.redis_settings,
        burst=True
    )
    await worker.main()
    
    # 4. Verify Job is discovered and Canonicalized
    res = await async_db_session.execute(select(Job).where(Job.company_name == "testco"))
    jobs = res.scalars().all()
    assert len(jobs) >= 1
    job = jobs[0]
    job_id = job.id
    assert job.title.lower() == "senior python engineer"
        
    # 5. Verify JobRecommendation is created
    res = await async_db_session.execute(select(JobRecommendation).where(
        JobRecommendation.profile_id == profile_id,
        JobRecommendation.job_id == job_id
    ))
    recs = res.scalars().all()
    assert len(recs) == 1
    rec = recs[0]
    assert rec.job_id == job_id
        
    # 6. User clicks "Apply"
    resp = await client.post("/applications", json={"job_id": job_id, "profile_id": profile_id})
    assert resp.status_code == 201
    app_id = resp.json()["id"]
    
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
    ])
    assert update_resp.status_code == 200
    assert len(update_resp.json()["unanswered"]) == 0
    
    # 7. Explicit Approval API
    resp = await client.post(f"/applications/{app_id}/approve", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"
    
    # 8. Trigger Submission
    resp = await client.post(f"/applications/{app_id}/submit")
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

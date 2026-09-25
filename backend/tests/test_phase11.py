import pytest
import asyncio
import uuid
from sqlalchemy import select, delete
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database.models import Base, Job, Profile, JobStatus, Application, ApplicationStatus, Task, TaskStatus

@pytest.fixture
async def client():
    class FakeRedisPool:
        async def enqueue_job(self, *args, **kwargs):
            return True
            
    app.state.redis = FakeRedisPool()
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
        
    app.state.redis = None

@pytest.fixture(autouse=True)
def mock_url_validator(monkeypatch):
    from app.core.security import UrlValidator
    def fake_validate(url):
        return url, "127.0.0.1"
    monkeypatch.setattr(UrlValidator, "validate_and_resolve", fake_validate)

@pytest.mark.asyncio
async def test_duplicate_application_prevention(client, async_db_session):
    job_id = f"job_test_{uuid.uuid4().hex[:8]}"
    profile_id = f"profile_{uuid.uuid4().hex[:8]}"
    
    job = Job(id=job_id, title="Test Engineer", company_name="Mock ATS", canonical_apply_url="http://localhost:8000/mock-ats/job/job_test_1/apply", status=JobStatus.ACTIVE)
    profile = Profile(is_active=True, id=profile_id, name="Alice Bob", email="alice@example.com", phone="1234567890")
    
    async_db_session.add(job)
    async_db_session.add(profile)
    await async_db_session.commit()

    # Create application
    resp = await client.post("/applications", json={"job_id": job_id}, headers={"X-Profile-ID": profile_id})
    assert resp.status_code == 201
    
    # Create again -> conflict
    resp2 = await client.post("/applications", json={"job_id": job_id}, headers={"X-Profile-ID": profile_id})
    assert resp2.status_code == 409
    
@pytest.mark.asyncio
async def test_authorization_checks(client, async_db_session):
    job_id = f"job_test_{uuid.uuid4().hex[:8]}"
    profile_id = f"profile_{uuid.uuid4().hex[:8]}"
    profile2_id = f"profile_{uuid.uuid4().hex[:8]}"
    
    job = Job(id=job_id, title="Test Engineer", company_name="Mock ATS", canonical_apply_url="http://localhost:8000/mock-ats/job/job_test_1/apply", status=JobStatus.ACTIVE)
    profile = Profile(is_active=True, id=profile_id, name="Alice Bob")
    profile2 = Profile(is_active=True, id=profile2_id, name="Eve Bob")
    
    async_db_session.add_all([job, profile, profile2])
    await async_db_session.commit()
    
    resp = await client.post("/applications", json={"job_id": job_id}, headers={"X-Profile-ID": profile_id})
    assert resp.status_code == 201
    app_id = resp.json()["id"]
    
    # Cannot get someone else's app
    resp2 = await client.get(f"/applications/{app_id}", headers={"X-Profile-ID": profile2_id})
    assert resp2.status_code == 403
    
    # Cannot approve someone else's app
    resp3 = await client.post(f"/applications/{app_id}/approve", json={}, headers={"X-Profile-ID": profile2_id})
    assert resp3.status_code == 403

@pytest.mark.asyncio
async def test_approval_flow_state_machine(client, async_db_session):
    job_id = f"job_test_{uuid.uuid4().hex[:8]}"
    profile_id = f"profile_{uuid.uuid4().hex[:8]}"
    
    job = Job(id=job_id, title="Test Engineer", company_name="Mock ATS", canonical_apply_url="http://localhost:8000/mock-ats/job/job_test_1/apply", status=JobStatus.ACTIVE)
    profile = Profile(is_active=True, id=profile_id, name="Alice Bob")
    async_db_session.add_all([job, profile])
    await async_db_session.commit()
    
    # Setup App
    resp = await client.post("/applications", json={"job_id": job_id}, headers={"X-Profile-ID": profile_id})
    app_id = resp.json()["id"]
    
    # Cannot approve in PREPARING
    resp2 = await client.post(f"/applications/{app_id}/approve", headers={"X-Profile-ID": profile_id}, json={})
    assert resp2.status_code == 400
    
    # Manually transition to READY_FOR_REVIEW
    app_record = await async_db_session.get(Application, app_id)
    app_record.status = ApplicationStatus.READY_FOR_REVIEW
    app_record.fields = []
    app_record.unanswered_required_fields = []
    await async_db_session.commit()
    
    # Now can approve
    resp3 = await client.post(f"/applications/{app_id}/approve", headers={"X-Profile-ID": profile_id}, json={})
    assert resp3.status_code == 200
    assert resp3.json()["status"] == "APPROVED"
    
    # Cannot submit if unapproved
    await async_db_session.refresh(app_record)
    app_record.status = ApplicationStatus.READY_FOR_REVIEW
    await async_db_session.commit()
    
    resp4 = await client.post(f"/applications/{app_id}/submit", headers={"X-Profile-ID": profile_id})
    assert resp4.status_code == 400

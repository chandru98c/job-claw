import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
import uuid

from app.database.models import Profile, Job, JobRecommendation, RecommendationState, Application, ApplicationStatus, Task, TaskStatus
from app.main import app

@pytest.fixture
async def client():
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

@pytest.fixture
async def setup_data(async_db_session: AsyncSession):
    profile_id = str(uuid.uuid4())
    other_profile_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    
    # Create profiles
    async_db_session.add(Profile(is_active=True, id=profile_id, name="Test1"))
    async_db_session.add(Profile(is_active=True, id=other_profile_id, name="Test2"))
    
    # Create job
    async_db_session.add(Job(id=job_id, title="Test Job", company_name="Test Company", canonical_apply_url="http://test.com/apply"))
    
    await async_db_session.commit()
    
    yield profile_id, other_profile_id, job_id
    
    # Cleanup
    from app.database.models import TaskEvent
    await async_db_session.execute(delete(JobRecommendation))
    await async_db_session.execute(delete(TaskEvent))
    await async_db_session.execute(delete(Task))
    await async_db_session.execute(delete(Application))
    await async_db_session.execute(delete(Job).where(Job.id == job_id))
    await async_db_session.execute(delete(Profile).where(Profile.id.in_([profile_id, other_profile_id])))
    await async_db_session.commit()

@pytest.mark.asyncio
async def test_prepare_contract(client: AsyncClient, async_db_session: AsyncSession, setup_data):
    profile_id, other_profile_id, job_id = setup_data
    
    # Mock authentication
    client.headers["X-Profile-ID"] = profile_id
    
    # Create a recommendation
    rec_id = str(uuid.uuid4())
    rec = JobRecommendation(
        id=rec_id,
        profile_id=profile_id,
        job_id=job_id,
        score=95,
        state=RecommendationState.NEW
    )
    async_db_session.add(rec)
    await async_db_session.commit()
    
    # Test non-prepare action (dismiss)
    resp = await client.post(f"/recommendations/{rec_id}/action", json={"action": "dismiss"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "DISMISSED"
    assert data.get("application_id") is None
    assert data.get("task_id") is None
    
    # Reset state to NEW for next test
    rec.state = RecommendationState.NEW
    await async_db_session.commit()
    
    # Test prepare action
    resp = await client.post(f"/recommendations/{rec_id}/action", json={"action": "prepare"})
    assert resp.status_code == 200
    data = resp.json()
    
    # Recommendation state is unchanged semantics
    assert data["state"] == "APPLIED"
    
    # Contract is fulfilled
    app_id = data.get("application_id")
    task_id = data.get("task_id")
    assert app_id is not None
    assert task_id is not None
    
    # Returned Application actually exists
    app_record = await async_db_session.get(Application, app_id)
    assert app_record is not None
    assert app_record.profile_id == profile_id
    assert app_record.job_id == job_id
    
    # Application begins in expected PREPARING state
    assert app_record.status == ApplicationStatus.PREPARING
    
    # Returned task corresponds to the preparation operation
    task_record = await async_db_session.get(Task, task_id)
    assert task_record is not None
    assert task_record.target_id == app_id
    assert task_record.worker_type == "prepare_application_task"
    
    # Test duplicate prepare behavior (idempotency)
    resp2 = await client.post(f"/recommendations/{rec_id}/action", json={"action": "prepare"})
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["application_id"] == app_id
    assert data2["task_id"] is None # We didn't create a new task
    
    # Test ownership rules
    client.headers["X-Profile-ID"] = other_profile_id
    resp_other = await client.post(f"/recommendations/{rec_id}/action", json={"action": "prepare"})
    assert resp_other.status_code == 404 # Should not find recommendation belonging to first profile

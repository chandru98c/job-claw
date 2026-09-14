import pytest
import pytest_asyncio
import uuid
import asyncio
from httpx import AsyncClient
from datetime import datetime, timezone

from app.main import app
from app.database.database import get_db, AsyncSessionLocal
from app.database.models import Profile, SavedSearch, JobRecommendation, RecommendationState, Source, Job, JobStatus, Application, ApplicationStatus
from app.schemas.saved_search import SavedSearchCreate
from app.schemas.search import SearchQuery

@pytest_asyncio.fixture
async def setup_test_data():
    async with AsyncSessionLocal() as db:
        # Create profile
        profile_id = f"test_profile_{uuid.uuid4().hex[:8]}"
        profile = Profile(id=profile_id, name="Test Profile P12")
        db.add(profile)
        
        # Create an active source
        domain_name = f"testats_{uuid.uuid4().hex[:8]}.com"
        source = Source(id=str(uuid.uuid4()), domain=domain_name, start_url=f"https://{domain_name}/jobs", is_active=True)
        db.add(source)
        
        # Create a mock job to match
        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            title="Senior Python Backend Developer",
            company_name="Test Company",
            location="Remote",
            canonical_apply_url="https://testats.com/jobs/123/apply",
            status=JobStatus.ACTIVE
        )
        db.add(job)
        await db.commit()
        
        yield {"profile_id": profile_id, "job_id": job_id}

@pytest.mark.asyncio
async def test_saved_search_crud(setup_test_data):
    # This requires overriding `get_current_profile_id` if we hit the actual endpoints,
    # or testing the DB models directly. Since we're in tests and `get_current_profile_id` 
    # currently returns "default_profile_id", let's test DB directly for simplicity.
    profile_id = setup_test_data["profile_id"]
    
    async with AsyncSessionLocal() as db:
        # Create
        search = SavedSearch(
            profile_id=profile_id,
            name="Python Roles",
            query="Python",
            location="Remote"
        )
        db.add(search)
        await db.commit()
        await db.refresh(search)
        
        assert search.id is not None
        assert search.enabled is True
        
        # Update
        search.enabled = False
        await db.commit()
        await db.refresh(search)
        assert search.enabled is False
        
        # Delete
        await db.delete(search)
        await db.commit()

@pytest.mark.asyncio
async def test_recommendation_action_boundary(setup_test_data):
    """
    Test that 'prepare' action creates an Application in PREPARING
    state and DOES NOT automatically submit it.
    """
    profile_id = setup_test_data["profile_id"]
    job_id = setup_test_data["job_id"]
    
    async with AsyncSessionLocal() as db:
        rec = JobRecommendation(
            profile_id=profile_id,
            job_id=job_id,
            score=85,
            state=RecommendationState.NEW
        )
        db.add(rec)
        await db.commit()
        await db.refresh(rec)
        
        # Simulate action
        class DummyRequest:
            class App:
                class State:
                    class Redis:
                        async def enqueue_job(self, *args, **kwargs):
                            pass
                    redis = Redis()
                state = State()
            app = App()
            
        from app.api.recommendations import recommendation_action
        from app.schemas.recommendation import RecommendationAction
        
        # Monkeypatch get_current_profile_id inside recommendations
        import app.api.recommendations as rec_api
        original_get = rec_api.get_current_profile_id
        rec_api.get_current_profile_id = lambda r: profile_id
        
        try:
            await recommendation_action(
                rec.id, 
                RecommendationAction(action="prepare"), 
                DummyRequest(), 
                db
            )
            
            # Verify Application state
            from sqlalchemy import select
            app_res = await db.execute(select(Application).where(Application.profile_id == profile_id))
            application = app_res.scalar_one()
            
            assert application is not None
            assert application.status == ApplicationStatus.PREPARING
            # It must not be SUBMITTED
            assert application.status != ApplicationStatus.SUBMITTED
            
        finally:
            rec_api.get_current_profile_id = original_get

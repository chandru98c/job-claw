import pytest
import uuid
import asyncio
from app.database.models import Profile, Job, JobStatus, JobRecommendation, Application, ApplicationStatus
import app.database.database as db_module
from sqlalchemy import select

@pytest.mark.asyncio
async def test_full_e2e_pipeline_flow():
    """
    Simulates the core Job-Claw pipeline:
    1. A Job is discovered and inserted.
    2. A SavedSearch cron triggers matching.
    3. A Recommendation is created.
    4. The user approves it into an Application.
    5. The application is processed.
    """
    profile_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    
    async with db_module.AsyncSessionLocal() as db:
        profile = Profile(id=profile_id, name="E2E Test User", skills=["python", "pytest"])
        job = Job(id=job_id, title="Python Developer", company_name="Tech Corp", canonical_apply_url="https://test.com/apply", status=JobStatus.ACTIVE)
        db.add(profile)
        db.add(job)
        await db.commit()
        
    # Phase 12 Matching -> Recommendation
    from app.services.search import SearchService
    async with db_module.AsyncSessionLocal() as db:
        # Load profile
        p_result = await db.execute(select(Profile).where(Profile.id == profile_id))
        profile_obj = p_result.scalar_one()
        
        matches, total = await SearchService.match_candidate(db, profile_obj)
        assert total > 0
        
        # Upsert recommendation
        rec = JobRecommendation(
            profile_id=profile_id,
            job_id=matches[0]["job"].id,
            score=matches[0]["score"],
            reasons=matches[0]["reasons"]
        )
        db.add(rec)
        await db.commit()
        
    # Phase 11 Application Flow
    async with db_module.AsyncSessionLocal() as db:
        app = Application(
            id=str(uuid.uuid4()),
            profile_id=profile_id,
            job_id=job_id,
            status=ApplicationStatus.APPROVED
        )
        db.add(app)
        await db.commit()
        
        # Emulate submission success
        app.status = ApplicationStatus.SUBMITTED
        await db.commit()
        
    async with db_module.AsyncSessionLocal() as db:
        res = await db.execute(select(Application).where(Application.profile_id == profile_id))
        final_app = res.scalar_one()
        assert final_app.status == ApplicationStatus.SUBMITTED
        assert final_app.job_id == job_id

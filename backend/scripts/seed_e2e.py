import asyncio
import uuid
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

from app.database.database import engine, Base, AsyncSessionLocal
from app.database.models import *

async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    async with AsyncSessionLocal() as session:
        profile_id = "default_profile_id"
        profile = Profile(id=profile_id, name="Test User", email="test@example.com")
        session.add(profile)
        
        job_id = "11111111-1111-1111-1111-111111111111"
        job = Job(
            id=job_id,
            title="E2E Test Software Engineer",
            company_name="Mock ATS Inc.",
            canonical_apply_url=f"http://127.0.0.1:8000/mock-ats/job/mock1/apply",
            description="A job for testing"
        )
        session.add(job)
        
        rec_id = "11111111-1111-1111-1111-222222222222"
        rec = JobRecommendation(
            id=rec_id,
            profile_id=profile_id,
            job_id=job_id,
            score=95,
            state=RecommendationState.NEW
        )
        session.add(rec)
        
        # Job 2: For failure
        job2_id = "22222222-2222-2222-2222-111111111111"
        job2 = Job(id=job2_id, title="Fail Job", company_name="Mock", canonical_apply_url=f"http://127.0.0.1:8000/mock-ats/job/mock2/apply?fail=true", description="x")
        session.add(job2)
        rec2 = JobRecommendation(id="22222222-2222-2222-2222-222222222222", profile_id=profile_id, job_id=job2_id, score=90, state=RecommendationState.NEW)
        session.add(rec2)
        
        # Job 3: For unknown
        job3_id = "33333333-3333-3333-3333-111111111111"
        job3 = Job(id=job3_id, title="Unknown Job", company_name="Mock", canonical_apply_url=f"http://127.0.0.1:8000/mock-ats/job/{job3_id}/apply?unknown=true", description="x")
        session.add(job3)
        rec3 = JobRecommendation(id="33333333-3333-3333-3333-222222222222", profile_id=profile_id, job_id=job3_id, score=90, state=RecommendationState.NEW)
        session.add(rec3)

        await session.commit()
        print("E2E Seed complete (Deterministic IDs)")

if __name__ == "__main__":
    asyncio.run(seed())

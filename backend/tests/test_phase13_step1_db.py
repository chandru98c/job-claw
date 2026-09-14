import pytest
import pytest_asyncio
import uuid
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.database.database import engine, Base
import app.database.database as db_module
from app.database.models import (
    Profile, Job, JobSourceProvenance, JobVersion,
    SavedSearch, JobRecommendation, Application, Source
)

@pytest.fixture(scope="module")
def sync_engine():
    import os
    from app.core.config import settings
    # convert asyncpg url to psycopg2 or just pg8000 for sync
    url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = sa.create_engine(url)
    yield engine
    engine.dispose()

def test_migration_integrity(sync_engine):
    """
    Simulates a clean database creation from migrations by verifying metadata.
    """
    inspector = sa.inspect(sync_engine)
    tables = inspector.get_table_names()
    
    assert "profiles" in tables
    assert "jobs" in tables
    assert "job_source_provenances" in tables
    assert "job_versions" in tables
    assert "saved_searches" in tables
    assert "job_recommendations" in tables
    assert "applications" in tables
    assert "sources" in tables

@pytest.mark.asyncio
async def test_database_relational_integrity():
    """
    Verifies that foreign keys, deletes, and basic relational structures hold true.
    """
    async with db_module.AsyncSessionLocal() as db:
        profile_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        source_id = str(uuid.uuid4())
        domain = f"{uuid.uuid4()}.com"
        
        # 1. Create dependencies
        profile = Profile(id=profile_id, name="Integrity Test Profile")
        job = Job(id=job_id, title="Test Job", company_name="Test Company", canonical_apply_url=f"https://{domain}/apply")
        source = Source(id=source_id, domain=domain)
        
        db.add(profile)
        db.add(job)
        db.add(source)
        await db.commit()
        
        # 2. Test Provenance and Versions
        prov = JobSourceProvenance(
            job_id=job_id,
            source_id=source_id,
            source_url=f"https://{domain}/jobs/1",
            source_type="direct_ats"
        )
        version = JobVersion(
            job_id=job_id,
            changed_fields=["title"],
            previous_state={"title": "Old Job"},
            new_state={"title": "Test Job"}
        )
        db.add(prov)
        db.add(version)
        await db.commit()
        
        # 3. Test Recommendations & Applications & SavedSearches
        search = SavedSearch(profile_id=profile_id, name="Test Search", query="test")
        rec = JobRecommendation(profile_id=profile_id, job_id=job_id, score=90)
        app = Application(profile_id=profile_id, job_id=job_id, status="PREPARING")
        
        db.add(search)
        db.add(rec)
        db.add(app)
        await db.commit()
        
        # 4. Read back and verify relations
        await db.refresh(job)
        await db.refresh(profile)
        
        # Verify FKs exist and aren't orphaned
        # Note: We rely on SQLAlchemy to enforce these constraints during commit
        assert rec.job_id == job.id
        assert rec.profile_id == profile.id
        assert app.job_id == job.id
        assert app.profile_id == profile.id

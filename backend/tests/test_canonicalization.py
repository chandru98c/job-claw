import pytest
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone, timedelta

from app.schemas.discovery import RawJob, DiscoveryProvenanceDTO
from app.canonicalization.pipeline import process_raw_job
from app.database.models import Base, Job, JobSourceProvenance, JobVersion, JobStatus, Source
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

def create_raw_job(source_id: str, source_job_id: str, title: str, company: str, apply_url: str = None, location: str = None, source_type: str = "direct_ats", provider_name: str = "TestATS", target_url: str = "https://example.com/api/jobs") -> RawJob:
    return RawJob(
        title=title,
        company=company,
        location=location,
        provenance=DiscoveryProvenanceDTO(
            strategy_id="test_strat",
            source_id=source_id,
            source_type=source_type,
            source_job_id=source_job_id,
            source_url=target_url,
            apply_url=apply_url,
            provider_name=provider_name
        )
    )

def test_A_same_source_same_job_id(db_session: Session):
    # Same source + same source_job_id -> one Job (idempotent)
    job1 = create_raw_job("src_1", "123", "Engineer", "Acme")
    res1, db_job1 = process_raw_job(db_session, job1)
    
    job2 = create_raw_job("src_1", "123", "Engineer", "Acme")
    res2, db_job2 = process_raw_job(db_session, job2)
    
    assert res1 == "NEW"
    assert res2 == "SAME"
    assert db_job1.id == db_job2.id
    assert db_session.query(Job).count() == 1
    assert db_session.query(JobSourceProvenance).count() == 1

def test_B_same_source_different_job_id(db_session: Session):
    # Same source + different source_job_id -> two Jobs
    job1 = create_raw_job("src_1", "123", "Engineer", "Acme")
    process_raw_job(db_session, job1)
    
    job2 = create_raw_job("src_1", "456", "Engineer", "Acme")
    res2, db_job2 = process_raw_job(db_session, job2)
    
    assert res2 == "NEW"
    assert db_session.query(Job).count() == 2

def test_C_different_sources_same_job_id(db_session: Session):
    # Different sources + same source_job_id -> verify source-scoped identity (Two Jobs)
    job1 = create_raw_job("src_1", "123", "Engineer", "Acme")
    process_raw_job(db_session, job1)
    
    job2 = create_raw_job("src_2", "123", "Designer", "Globex")
    res2, db_job2 = process_raw_job(db_session, job2)
    
    assert res2 == "NEW"
    assert db_session.query(Job).count() == 2

def test_D_same_canonical_apply_url(db_session: Session):
    # Same canonical apply URL -> one Job
    job1 = create_raw_job("src_1", "123", "Engineer", "Acme", apply_url="https://acme.com/jobs/99")
    process_raw_job(db_session, job1)
    
    # Different source, different ID, but exact same apply URL
    job2 = create_raw_job("src_2", "456", "Software Engineer", "Acme Corp", apply_url="https://acme.com/jobs/99")
    res2, db_job2 = process_raw_job(db_session, job2)
    
    assert res2 == "UPDATED" # Because title changes from Engineer -> Software Engineer, triggering version bump
    assert db_session.query(Job).count() == 1
    
    # Verify both provenances are retained
    assert db_session.query(JobSourceProvenance).count() == 2

def test_E_same_apply_url_with_tracking(db_session: Session):
    # Same apply URL + tracking parameters -> one Job
    job1 = create_raw_job("src_1", "123", "Engineer", "Acme", apply_url="https://acme.com/jobs/99")
    process_raw_job(db_session, job1)
    
    # URL with tracking params
    job2 = create_raw_job("src_2", "456", "Engineer", "Acme", apply_url="https://acme.com/jobs/99?utm_source=linkedin&gh_src=test")
    res2, db_job2 = process_raw_job(db_session, job2)
    
    assert res2 == "SAME" # Title unchanged, no fields updated, but matched on URL
    assert db_session.query(Job).count() == 1
    assert db_session.query(JobSourceProvenance).count() == 2

def test_E_gh_jid_is_preserved(db_session: Session):
    # gh_jid is NOT stripped, so different gh_jid means different job
    job1 = create_raw_job("src_1", "123", "Engineer 1", "Acme", apply_url="https://acme.com/jobs?gh_jid=111")
    process_raw_job(db_session, job1)
    
    job2 = create_raw_job("src_2", "456", "Engineer 2", "Acme", apply_url="https://acme.com/jobs?gh_jid=222")
    process_raw_job(db_session, job2)
    
    assert db_session.query(Job).count() == 2

def test_F_same_collection_endpoint(db_session: Session):
    # Same collection endpoint + different ATS IDs -> multiple Jobs
    job1 = create_raw_job("src_1", "123", "Engineer", "Acme", target_url="https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true")
    process_raw_job(db_session, job1)
    
    job2 = create_raw_job("src_1", "456", "Designer", "Acme", target_url="https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true")
    process_raw_job(db_session, job2)
    
    assert db_session.query(Job).count() == 2

def test_G_same_company_title_location(db_session: Session):
    # Same company/title/location -> deterministic fallback behavior
    job1 = create_raw_job(None, None, "Senior Backend Engineer", "Globex Corporation", location="San Francisco, CA")
    process_raw_job(db_session, job1)
    
    # Slightly different formatting, no apply url, no source ID
    job2 = create_raw_job(None, None, "Senior Backend Engineer", "Globex Corp.", location="San Francisco CA")
    res2, db_job2 = process_raw_job(db_session, job2)
    
    assert res2 == "SAME"
    assert db_session.query(Job).count() == 1

def test_H_different_titles_no_merge(db_session: Session):
    # Different titles -> no unsafe merge
    job1 = create_raw_job(None, None, "Software Engineer", "Globex", location="SF")
    process_raw_job(db_session, job1)
    
    job2 = create_raw_job(None, None, "Senior Software Engineer", "Globex", location="SF")
    res2, db_job2 = process_raw_job(db_session, job2)
    
    assert res2 == "NEW"
    assert db_session.query(Job).count() == 2

def test_I_different_locations_no_merge(db_session: Session):
    # Different locations -> no unsafe merge
    job1 = create_raw_job(None, None, "Software Engineer", "Globex", location="Chennai")
    process_raw_job(db_session, job1)
    
    job2 = create_raw_job(None, None, "Software Engineer", "Globex", location="Bangalore")
    res2, db_job2 = process_raw_job(db_session, job2)
    
    assert res2 == "NEW"
    assert db_session.query(Job).count() == 2

def test_J_multiple_provenance(db_session: Session):
    # Same job discovered by two sources -> one Job + multiple provenance records
    job1 = create_raw_job("src_1", "123", "Engineer", "Acme", apply_url="https://acme.com/jobs/99")
    process_raw_job(db_session, job1)
    
    job2 = create_raw_job("src_2", "456", "Engineer", "Acme", apply_url="https://acme.com/jobs/99")
    res2, db_job2 = process_raw_job(db_session, job2)
    
    assert res2 == "SAME"
    assert db_session.query(Job).count() == 1
    assert db_session.query(JobSourceProvenance).count() == 2

def test_K_repeated_discovery(db_session: Session):
    # Repeated discovery -> idempotent
    job1 = create_raw_job("src_1", "123", "Engineer", "Acme", apply_url="https://acme.com/jobs/99")
    process_raw_job(db_session, job1)
    process_raw_job(db_session, job1)
    process_raw_job(db_session, job1)
    
    assert db_session.query(Job).count() == 1
    assert db_session.query(JobSourceProvenance).count() == 1

def test_L_concurrent_duplicate_discovery(db_session: Session):
    # Concurrent duplicate discovery -> no duplicate canonical Jobs
    job1 = create_raw_job("src_1", "123", "Engineer", "Acme")
    _, db_job1 = process_raw_job(db_session, job1)
    
    job2 = Job(
        title="Concurrent Engineer",
        company_name="Acme",
        canonical_apply_url="https://acme.com/another"
    )
    db_session.add(job2)
    db_session.commit()
    
    prov2 = JobSourceProvenance(
        job_id=job2.id,
        source_id="src_1",
        source_type="direct_ats",
        source_job_id="123",
        source_url="https://example.com"
    )
    db_session.add(prov2)
    
    with pytest.raises(IntegrityError):
        db_session.commit()

def test_M_metadata_update(db_session: Session):
    # Metadata update -> existing Job updated
    job1 = create_raw_job("src_1", "123", "Engineer", "Acme")
    job1.description = "Old description"
    process_raw_job(db_session, job1)
    
    job2 = create_raw_job("src_1", "123", "Engineer", "Acme")
    job2.description = "New description"
    res2, db_job2 = process_raw_job(db_session, job2)
    
    assert res2 == "UPDATED"
    assert db_session.query(Job).count() == 1
    
    updated_job = db_session.query(Job).first()
    assert updated_job.description == "New description"
    
    assert db_session.query(JobVersion).count() == 1
    version = db_session.query(JobVersion).first()
    assert "description" in version.changed_fields

def test_N_provenance_retained(db_session: Session):
    # Provenance retained after update
    job1 = create_raw_job("src_1", "123", "Engineer", "Acme")
    process_raw_job(db_session, job1)
    
    job2 = create_raw_job("src_1", "123", "Engineer Sr", "Acme")
    process_raw_job(db_session, job2)
    
    assert db_session.query(JobSourceProvenance).count() == 1
    prov = db_session.query(JobSourceProvenance).first()
    assert prov.source_job_id == "123"


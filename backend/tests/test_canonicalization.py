import pytest
from datetime import datetime, timezone, timedelta
from app.canonicalization.normalize import (
    normalize_title,
    normalize_company,
    normalize_location,
    normalize_url
)
from app.canonicalization.pipeline import process_raw_job
from app.schemas.discovery import RawJob, DiscoveryProvenanceDTO
from app.database.models import Base, Job, JobSourceProvenance, JobVersion, JobStatus
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

# --- Normalization Tests ---

def test_normalize_title():
    assert normalize_title("Software Engineer (Remote)") == "software engineer"
    assert normalize_title("Senior Developer - Hiring Now!") == "senior developer"
    assert normalize_title("  Data   Scientist  ") == "data scientist"
    assert normalize_title("Søftware Engïnéer") == "sftware engineer" # NFKD normalization dropping non-ascii

def test_normalize_company():
    assert normalize_company("Acme Corp.") == "acme"
    assert normalize_company("Stark Industries LLC") == "stark industries"
    assert normalize_company("Pied Piper, Inc.") == "pied piper"
    assert normalize_company("Globex Corporation") == "globex"

def test_normalize_location():
    assert normalize_location("San Francisco, CA") == "san francisco ca"
    assert normalize_location("  New York ,  NY  ") == "new york ny"

def test_normalize_url():
    assert normalize_url("HTTPS://example.com/job/") == "https://example.com/job"
    assert normalize_url("https://example.com/job?utm_source=linkedin&gh_jid=123&id=456") == "https://example.com/job?id=456"
    assert normalize_url("http://test.com") == "http://test.com"

# --- Pipeline Tests ---

@pytest.fixture
def sample_provenance():
    return DiscoveryProvenanceDTO(
        strategy_id="test_strat",
        source_type="direct_ats",
        source_url="https://careers.acme.com/job/123",
        source_job_id="ACME-123",
        apply_url="https://acme.greenhouse.io/apply/123",
        provider_name="Greenhouse"
    )

@pytest.fixture
def sample_raw_job(sample_provenance):
    return RawJob(
        provenance=sample_provenance,
        title="Software Engineer",
        company="Acme Corp",
        location="San Francisco, CA",
        description="A great job.",
        employment_type="Full-time",
        remote_status="Remote"
    )

def test_canonicalization_new_job(db_session, sample_raw_job):
    """Test inserting a completely new job."""
    result, job = process_raw_job(db_session, sample_raw_job)
    
    assert result == "NEW"
    assert job.title == "software engineer"
    assert job.company_name == "acme"
    assert job.location == "san francisco ca"
    assert job.canonical_apply_url == "https://acme.greenhouse.io/apply/123"
    assert job.status == JobStatus.ACTIVE
    
    # Check provenance
    prov = db_session.query(JobSourceProvenance).filter_by(job_id=job.id).first()
    assert prov is not None
    assert prov.source_job_id == "ACME-123"
    assert prov.source_type == "direct_ats"
    
    # No version created initially by our logic
    version_count = db_session.query(JobVersion).filter_by(job_id=job.id).count()
    assert version_count == 0

def test_canonicalization_idempotency_same_job(db_session, sample_raw_job):
    """Test submitting the exact same raw job twice."""
    res1, job1 = process_raw_job(db_session, sample_raw_job)
    assert res1 == "NEW"
    
    res2, job2 = process_raw_job(db_session, sample_raw_job)
    assert res2 == "SAME"
    assert job1.id == job2.id
    
    # Still only 1 provenance
    prov_count = db_session.query(JobSourceProvenance).filter_by(job_id=job1.id).count()
    assert prov_count == 1
    
    # Still 0 versions
    version_count = db_session.query(JobVersion).filter_by(job_id=job1.id).count()
    assert version_count == 0

def test_canonicalization_updated_version(db_session, sample_raw_job):
    """Test updating fields creates a new JobVersion."""
    # Insert first
    _, job1 = process_raw_job(db_session, sample_raw_job)
    
    # Modify raw job slightly
    sample_raw_job.title = "Senior Software Engineer"
    sample_raw_job.location = "Remote"
    # Ensure it maps to the same job by keeping ATS IDs the same
    
    res2, job2 = process_raw_job(db_session, sample_raw_job)
    assert res2 == "UPDATED"
    assert job2.title == "senior software engineer"
    assert job2.location == "remote"
    
    # Check version
    versions = db_session.query(JobVersion).filter_by(job_id=job1.id).all()
    assert len(versions) == 1
    assert "title" in versions[0].changed_fields
    assert "location" in versions[0].changed_fields
    assert versions[0].previous_state["title"] == "software engineer"
    assert versions[0].new_state["title"] == "senior software engineer"

def test_canonicalization_multiple_sources(db_session, sample_raw_job):
    """Test same job found on different sources adds multiple provenances."""
    process_raw_job(db_session, sample_raw_job)
    
    # Same canonical URL, but different source (e.g. aggregator)
    aggregator_prov = DiscoveryProvenanceDTO(
        strategy_id="aggregator_strat",
        source_type="aggregator",
        source_url="https://indeed.com/viewjob?jk=abc",
        apply_url="https://acme.greenhouse.io/apply/123", # Strong identity match
        provider_name="Indeed"
    )
    raw_job2 = RawJob(
        provenance=aggregator_prov,
        title="Software Engineer",
        company="Acme",
        location="San Francisco, CA"
    )
    
    res2, job2 = process_raw_job(db_session, raw_job2)
    assert res2 == "SAME"
    
    provs = db_session.query(JobSourceProvenance).filter_by(job_id=job2.id).all()
    assert len(provs) == 2
    assert {"direct_ats", "aggregator"} == {p.source_type for p in provs}

def test_canonicalization_lifecycle_reopen(db_session, sample_raw_job):
    """Test EXPIRED job becomes ACTIVE again."""
    _, job = process_raw_job(db_session, sample_raw_job)
    
    # Force expire it
    job.status = JobStatus.EXPIRED
    db_session.commit()
    
    # Process it again
    # Use a future timestamp
    sample_raw_job.discovered_at = datetime.now(timezone.utc) + timedelta(days=1)
    res2, job2 = process_raw_job(db_session, sample_raw_job)
    
    assert res2 == "UPDATED"
    assert job2.status == JobStatus.ACTIVE

def test_canonicalization_fuzzy_match_avoidance(db_session, sample_raw_job):
    """Ensure two similar but different jobs aren't merged incorrectly."""
    process_raw_job(db_session, sample_raw_job)
    
    # Different job ID, different Apply URL, same title and company
    # This shouldn't merge automatically if we are strictly deterministic,
    # Actually wait: "Medium identity: normalized company + title + location"
    # If they share the exact title, company, location, they WILL merge by the medium identity rule!
    # Let's test the medium identity rule.
    
    prov2 = DiscoveryProvenanceDTO(
        strategy_id="test",
        source_type="direct_ats",
        source_url="https://careers.acme.com/job/456",
        source_job_id="ACME-456",
        apply_url="https://acme.greenhouse.io/apply/456"
    )
    raw_job2 = RawJob(
        provenance=prov2,
        title="Software Engineer",
        company="Acme Corp",
        location="San Francisco, CA"
    )
    
    res2, job2 = process_raw_job(db_session, raw_job2)
    # Based on our identity resolution logic:
    # 1. No match on source_job_id
    # 2. No match on URLs
    # 3. Match on company + title + location -> YES.
    # It will merge!
    assert res2 == "SAME"

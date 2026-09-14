import pytest
import httpx
from datetime import datetime, timezone, timedelta
from typing import AsyncIterator

from app.database.models import Job, JobStatus, JobSourceProvenance, Base, Task, TaskStatus
from app.verification.lifecycle import apply_verification_result
from app.schemas.verification import VerificationResult, VerificationOutcome, VerificationReason
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

@pytest.fixture
def sample_job(db_session):
    job = Job(
        title="Software Engineer",
        company_name="Acme",
        canonical_apply_url="https://acme.com/apply",
        status=JobStatus.ACTIVE,
        last_verified_at=datetime.now(timezone.utc) - timedelta(days=1)
    )
    db_session.add(job)
    db_session.commit()
    
    prov = JobSourceProvenance(
        job_id=job.id,
        source_url="https://careers.acme.com/job/123",
        source_type="direct_ats"
    )
    db_session.add(prov)
    db_session.commit()
    
    return job

def test_active_to_active(db_session, sample_job):
    result = VerificationResult(
        outcome=VerificationOutcome.CONFIRMED_PRESENT,
        reason=VerificationReason.ACTIVE_CONFIRMED,
        http_status=200,
        reachable=True
    )
    old_time = sample_job.last_verified_at
    
    new_status = apply_verification_result(db_session, sample_job.id, [result])
    db_session.refresh(sample_job)
    
    assert new_status == JobStatus.ACTIVE
    assert sample_job.status == JobStatus.ACTIVE
    assert sample_job.last_verified_at > old_time

def test_active_to_expired_404(db_session, sample_job):
    result = VerificationResult(
        outcome=VerificationOutcome.CONFIRMED_MISSING,
        reason=VerificationReason.HTTP_404,
        http_status=404,
        reachable=True,
        job_present=False
    )
    
    new_status = apply_verification_result(db_session, sample_job.id, [result])
    assert new_status == JobStatus.EXPIRED

def test_active_to_unknown_transient(db_session, sample_job):
    result = VerificationResult(
        outcome=VerificationOutcome.TRANSIENT_FAILURE,
        reason=VerificationReason.SERVER_ERROR,
        http_status=500,
        reachable=True
    )
    
    new_status = apply_verification_result(db_session, sample_job.id, [result])
    assert new_status == JobStatus.UNKNOWN
    # False-expiry protection: never expires on 500

def test_active_to_blocked(db_session, sample_job):
    result = VerificationResult(
        outcome=VerificationOutcome.BLOCKED,
        reason=VerificationReason.BLOCKED_BY_POLICY,
        http_status=None,
        reachable=False
    )
    
    new_status = apply_verification_result(db_session, sample_job.id, [result])
    assert new_status == JobStatus.BLOCKED

def test_ambiguous_200_never_expires(db_session, sample_job):
    result = VerificationResult(
        outcome=VerificationOutcome.AMBIGUOUS,
        reason=VerificationReason.AMBIGUOUS,
        http_status=200,
        reachable=True
    )
    new_status = apply_verification_result(db_session, sample_job.id, [result])
    # Ambiguous sets it to UNKNOWN (not EXPIRED)
    assert new_status == JobStatus.UNKNOWN

def test_stale_to_active(db_session, sample_job):
    sample_job.status = JobStatus.STALE
    db_session.commit()
    
    result = VerificationResult(
        outcome=VerificationOutcome.CONFIRMED_PRESENT,
        reason=VerificationReason.ACTIVE_CONFIRMED,
        http_status=200,
        reachable=True
    )
    
    new_status = apply_verification_result(db_session, sample_job.id, [result])
    assert new_status == JobStatus.ACTIVE

def test_multi_source_safety(db_session, sample_job):
    # Job has two sources
    prov2 = JobSourceProvenance(
        job_id=sample_job.id,
        source_url="https://aggregator.com/job",
        source_type="aggregator"
    )
    db_session.add(prov2)
    db_session.commit()
    
    # ATS returns 404, but aggregator is still active
    result1 = VerificationResult(
        outcome=VerificationOutcome.CONFIRMED_MISSING,
        reason=VerificationReason.HTTP_404,
        http_status=404,
        reachable=True
    )
    result2 = VerificationResult(
        outcome=VerificationOutcome.CONFIRMED_PRESENT,
        reason=VerificationReason.ACTIVE_CONFIRMED,
        http_status=200,
        reachable=True
    )
    
    new_status = apply_verification_result(db_session, sample_job.id, [result1, result2])
    # Active wins
    assert new_status == JobStatus.ACTIVE

def test_concurrency_protection(db_session, sample_job):
    # Simulate Worker B taking longer but producing ACTIVE, while Worker A produces MISSING and commits first
    # With row-level locking, the second transaction will wait for the first to complete.
    # In python test without threads, we just apply sequentially
    
    # Worker A
    res_a = VerificationResult(outcome=VerificationOutcome.CONFIRMED_MISSING, reason=VerificationReason.HTTP_404, reachable=True)
    apply_verification_result(db_session, sample_job.id, [res_a])
    
    # Worker B (started earlier, finishes later)
    # The job is now EXPIRED
    db_session.refresh(sample_job)
    assert sample_job.status == JobStatus.EXPIRED
    
    # B applies ACTIVE (which simulates the rediscovery logic or a late active result)
    res_b = VerificationResult(outcome=VerificationOutcome.CONFIRMED_PRESENT, reason=VerificationReason.ACTIVE_CONFIRMED, reachable=True)
    apply_verification_result(db_session, sample_job.id, [res_b])
    
    # Active overrules
    db_session.refresh(sample_job)
    assert sample_job.status == JobStatus.ACTIVE

# --- ARQ Worker Tests ---

@pytest.mark.asyncio
async def test_verification_worker_success(db_session, sample_job, monkeypatch):
    async def mock_verify_url(url, policy=None):
        return VerificationResult(
            outcome=VerificationOutcome.CONFIRMED_PRESENT,
            reason=VerificationReason.ACTIVE_CONFIRMED,
            http_status=200,
            reachable=True
        )
    monkeypatch.setattr('app.verification.verifier.VerificationEngine.verify_url', mock_verify_url)
    
    from app.workers.verification import verify_job_task
    ctx = {"job_id": "test-task-1", "job_try": 1}
    
    # Need to override SessionLocal in worker
    monkeypatch.setattr('app.workers.verification.SessionLocal', lambda: db_session)
    
    job_id = sample_job.id
    await verify_job_task(ctx, job_id=job_id)
    
    # Re-fetch because the worker called db.close() on our shared mock session
    sample_job = db_session.query(Job).filter_by(id=job_id).first()
    assert sample_job.status == JobStatus.ACTIVE
    
    task = db_session.query(Task).filter_by(id="test-task-1").first()
    assert task.status == TaskStatus.SUCCEEDED

@pytest.mark.asyncio
async def test_verification_worker_retry(db_session, sample_job, monkeypatch):
    async def mock_verify_url(url, policy=None):
        return VerificationResult(
            outcome=VerificationOutcome.TRANSIENT_FAILURE,
            reason=VerificationReason.RATE_LIMITED,
            http_status=429,
            reachable=True
        )
    monkeypatch.setattr('app.verification.verifier.VerificationEngine.verify_url', mock_verify_url)
    
    from app.workers.verification import verify_job_task
    from arq import Retry
    
    ctx = {"job_id": "test-task-2", "job_try": 1}
    monkeypatch.setattr('app.workers.verification.SessionLocal', lambda: db_session)
    
    job_id = sample_job.id
    with pytest.raises(Retry):
        await verify_job_task(ctx, job_id=job_id)
        
    sample_job = db_session.query(Job).filter_by(id=job_id).first()
    # The task should be RETRYING
    task = db_session.query(Task).filter_by(id="test-task-2").first()
    assert task.status == TaskStatus.RETRYING
    
    # And the job should be UNKNOWN (transient failure sets to UNKNOWN pending retry)
    assert sample_job.status == JobStatus.UNKNOWN

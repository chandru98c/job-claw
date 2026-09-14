import logging
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.database.models import Job, JobStatus, JobSourceProvenance
from app.schemas.verification import VerificationResult, VerificationOutcome

logger = logging.getLogger(__name__)

def apply_verification_result(db: Session, job_id: str, results: list[VerificationResult]) -> JobStatus:
    """
    Deterministically transitions the JobStatus based on the combined evidence
    from all of its sources.
    
    This enforces the False-Expiry protection rule.
    """
    job = db.query(Job).filter(Job.id == job_id).with_for_update().first()
    if not job:
        return JobStatus.UNKNOWN
        
    # We look at the best evidence across all sources
    has_confirmed_present = any(r.outcome == VerificationOutcome.CONFIRMED_PRESENT for r in results)
    has_ambiguous = any(r.outcome == VerificationOutcome.AMBIGUOUS for r in results)
    has_transient = any(r.outcome == VerificationOutcome.TRANSIENT_FAILURE for r in results)
    has_blocked = any(r.outcome == VerificationOutcome.BLOCKED for r in results)
    
    # Check if all sources are definitively missing
    all_missing = len(results) > 0 and all(r.outcome == VerificationOutcome.CONFIRMED_MISSING for r in results)

    new_status = job.status
    
    # 1. Active evidence always wins
    if has_confirmed_present:
        new_status = JobStatus.ACTIVE
        job.last_verified_at = datetime.now(timezone.utc)
        
    # 2. If it's ambiguous, we can't expire it. If it was Active, it stays Active or becomes Unknown.
    # The requirement: "ambiguous 200 -> never EXPIRED". 
    elif has_ambiguous:
        if job.status in (JobStatus.EXPIRED, JobStatus.UNKNOWN, JobStatus.STALE, JobStatus.BLOCKED, JobStatus.VERIFYING):
            # We don't have confirmation it's active, but we can't say it's expired.
            # If it was VERIFYING, it becomes UNKNOWN because we couldn't confirm.
            new_status = JobStatus.UNKNOWN
        # If it was ACTIVE, it might stay ACTIVE or UNKNOWN depending on policy.
        # But let's be safe and mark UNKNOWN so we don't assume ACTIVE without proof.
        elif job.status == JobStatus.ACTIVE:
            new_status = JobStatus.UNKNOWN
            
    # 3. If blocked, we mark as blocked
    elif has_blocked:
        new_status = JobStatus.BLOCKED
        
    # 4. If all sources are 404/410, it's definitively expired
    elif all_missing:
        new_status = JobStatus.EXPIRED
        
    # 5. Transient failures
    elif has_transient:
        new_status = JobStatus.UNKNOWN
        
    job.status = new_status
    db.add(job)
    db.commit()
    return new_status

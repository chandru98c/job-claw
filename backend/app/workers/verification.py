import logging
import json
from arq import Retry
from sqlalchemy.orm import Session
from app.database.database import SessionLocal
from app.database.models import Job, JobStatus, Task, TaskStatus, TaskEventType, TaskEvent
from app.verification.verifier import VerificationEngine
from app.verification.lifecycle import apply_verification_result

logger = logging.getLogger(__name__)

def _record_event(db: Session, task_id: str, event_type: TaskEventType, payload: dict):
    event = TaskEvent(task_id=task_id, event_type=event_type, payload=payload)
    db.add(event)
    db.commit()

async def verify_job_task(ctx, job_id: str):
    """
    ARQ Task to verify a job's freshness.
    1. Loads Job + Provenance
    2. Runs Secure HTTP Verification per provenance
    3. Emits TaskEvents
    4. Lifecycle updates
    """
    job_id_str = str(job_id)
    task_id = ctx.get("job_id")  # ARQ assigns this internally to `job_id`, which is the task's uuid
    
    db: Session = SessionLocal()
    try:
        # Create Task record if not exists
        task = db.query(Task).filter_by(id=task_id).first()
        if not task:
            task = Task(id=task_id, target_id=job_id_str, worker_type="VerificationWorker", status=TaskStatus.RUNNING)
            db.add(task)
            db.commit()
            
        _record_event(db, task_id, TaskEventType.STARTED, {"job_id": job_id_str})
        
        # 1. Load Job
        job = db.query(Job).filter_by(id=job_id_str).with_for_update().first()
        if not job:
            _record_event(db, task_id, TaskEventType.ERROR, {"error": "Job not found"})
            return
            
        if job.status == JobStatus.STALE:
            job.status = JobStatus.VERIFYING
            db.add(job)
            db.commit()
        else:
            db.commit() # release lock

        # Load provenances outside of lock
        job = db.query(Job).filter_by(id=job_id_str).first()
        urls_to_verify = [p.source_url for p in job.provenances if p.source_url]
        
        if not urls_to_verify:
            _record_event(db, task_id, TaskEventType.ERROR, {"error": "No source URLs to verify"})
            return
            
        # 2. Verify all URLs
        results = []
        for url in urls_to_verify:
            res = await VerificationEngine.verify_url(url)
            results.append(res)
            _record_event(db, task_id, TaskEventType.PROGRESS, {
                "url": url, 
                "outcome": res.outcome.value, 
                "reason": res.reason.value,
                "http_status": res.http_status
            })
            
        # 3. Transition Lifecycle
        # Concurrency safety: apply_verification_result acquires its own row-level lock
        final_status = apply_verification_result(db, job_id_str, results)
        
        _record_event(db, task_id, TaskEventType.COMPLETED, {"final_status": final_status.value})
        
        # 4. Check if we need to retry
        has_transient = any(r.outcome == "TRANSIENT_FAILURE" for r in results)
        if has_transient and ctx.get("job_try", 1) < 3: # 3 max retries
            task = db.query(Task).filter_by(id=task_id).first()
            task.status = TaskStatus.RETRYING
            db.add(task)
            db.commit()
            _record_event(db, task_id, TaskEventType.RETRY, {"message": "Transient failures detected, retrying."})
            raise Retry(defer=ctx.get("job_try", 1) * 10)
            
        # Otherwise, mark task complete
        task = db.query(Task).filter_by(id=task_id).first()
        task.status = TaskStatus.SUCCEEDED
        db.add(task)
        db.commit()

    except Retry:
        raise
    except Exception as e:
        logger.exception(f"Verification task failed for {job_id_str}")
        _record_event(db, task_id, TaskEventType.ERROR, {"error": str(e)[:200]})
        task = db.query(Task).filter_by(id=task_id).first()
        if task:
            task.status = TaskStatus.FAILED
            db.add(task)
            db.commit()
    finally:
        db.close()

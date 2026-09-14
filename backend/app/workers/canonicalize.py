import traceback
from typing import Dict, Any

from app.database.database import SessionLocal
from app.database.models import Task, TaskStatus, TaskEventType, TaskEvent
from app.schemas.discovery import RawJob
from app.canonicalization.pipeline import process_raw_job

async def canonicalize_job_task(ctx: Dict[Any, Any], task_id: str, raw_job_dict: dict) -> None:
    """
    ARQ task that wraps the canonicalization pipeline.
    It expects a RawJob dictionary payload.
    """
    db = SessionLocal()
    try:
        # 1. Start Task Event
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            # Note: in a real system, we'd log this heavily.
            return
            
        task.status = TaskStatus.RUNNING
        db.add(TaskEvent(task_id=task.id, event_type=TaskEventType.STARTED))
        db.commit()

        # 2. Parse RawJob
        raw_job = RawJob.model_validate(raw_job_dict)

        # 3. Process Transaction
        result, job = process_raw_job(db, raw_job)
        
        # 4. Success Event
        task.status = TaskStatus.SUCCEEDED
        db.add(TaskEvent(
            task_id=task.id, 
            event_type=TaskEventType.COMPLETED,
            payload={"resolution": result, "canonical_job_id": job.id}
        ))
        db.commit()

    except Exception as e:
        db.rollback()
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            db.add(TaskEvent(
                task_id=task.id,
                event_type=TaskEventType.ERROR,
                payload={"error": str(e), "traceback": traceback.format_exc()}
            ))
            db.commit()
        raise e
    finally:
        db.close()

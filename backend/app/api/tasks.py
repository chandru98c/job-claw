import uuid
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.database import get_db
from app.database.models import Task, TaskEvent, TaskStatus, TaskEventType

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("/", status_code=201)
async def create_task(request: Request, target_id: str = "dummy", worker_type: str = "discovery_task", db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text
    
    lock_id = hash(f"{worker_type}_{target_id}") & 0x7FFFFFFFFFFFFFFF
    await db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": lock_id})
    
    stmt = select(Task).where(
        Task.target_id == target_id,
        Task.worker_type == worker_type,
        Task.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING])
    )
    existing_task = (await db.execute(stmt)).scalar_one_or_none()
    
    if existing_task:
        return {"task_id": existing_task.id, "status": existing_task.status.value, "message": "Task already active"}
        
    print(f"Creating task {target_id}")
    task_id = str(uuid.uuid4())
    
    new_task = Task(
        id=task_id,
        target_id=target_id,
        worker_type=worker_type,
        status=TaskStatus.QUEUED
    )
    db.add(new_task)
    
    event = TaskEvent(
        task_id=task_id,
        event_type=TaskEventType.QUEUED,
        payload={"target_id": target_id}
    )
    db.add(event)
    
    print("Committing DB...")
    await db.commit()
    print("DB Committed.")
    
    redis_pool = getattr(request.app.state, "redis", None)
    if redis_pool is None:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    print("Enqueueing job...")
    job = await redis_pool.enqueue_job(worker_type, task_id, target_id, _job_id=task_id)
    print("Job enqueued.")
    if not job:
        raise HTTPException(status_code=500, detail="Failed to enqueue job in ARQ")
        
    return {"task_id": task_id, "status": TaskStatus.QUEUED.value}

@router.get("/active")
async def get_active_task(worker_type: str, target_id: str, db: AsyncSession = Depends(get_db)):
    """Fetches the most recent active task (QUEUED or RUNNING) for a given type and target."""
    from sqlalchemy import desc
    stmt = select(Task).where(
        Task.worker_type == worker_type,
        Task.target_id == target_id,
        Task.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING])
    ).order_by(desc(Task.created_at)).limit(1)
    
    task = (await db.execute(stmt)).scalar_one_or_none()
    
    if not task:
        return {"task_id": None}
        
    return {
        "task_id": task.id,
        "status": task.status.value,
        "target_id": task.target_id,
        "worker_type": task.worker_type
    }

@router.get("/{task_id}")
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """
    Fetches task status and basic info directly from PostgreSQL.
    """
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    return {
        "task_id": task.id,
        "status": task.status.value,
        "target_id": task.target_id,
        "worker_type": task.worker_type,
        "error": task.error,
        "retry_count": task.retry_count
    }

@router.post("/{task_id}/cancel")
async def cancel_task(request: Request, task_id: str, db: AsyncSession = Depends(get_db)):
    """
    Requests cooperative cancellation of a task.
    """
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    if task.status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED):
        raise HTTPException(status_code=400, detail="Task already finished")

    # Call ARQ abort
    redis_pool = getattr(request.app.state, "redis", None)
    if redis_pool is None:
        raise HTTPException(status_code=503, detail="Redis unavailable")
    # Try to abort the job via ARQ. The worker must have `allow_abort_jobs=True`
    # and catch `asyncio.CancelledError`.
    from arq.jobs import Job
    job = Job(task_id, redis_pool)
    aborted = await job.abort()
    
    # If the job was aborted successfully or was waiting, we can manually update the DB to CANCELLED
    # just in case the worker never picks it up. If it's already RUNNING, the CancelledError 
    # will update the DB. We'll mark it cancelling here for UI responsiveness.
    if aborted:
        setattr(task, "status", TaskStatus.CANCELLED)
        event = TaskEvent(task_id=task_id, event_type=TaskEventType.CANCELLED, payload={"reason": "User requested cancel"})
        db.add(event)
        await db.commit()
        return {"status": "cancelled", "message": "Task cancelled successfully."}
        
    return {"status": task.status.value, "message": "Abort signal sent, or task already completed."}

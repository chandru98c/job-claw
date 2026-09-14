import uuid
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.database import get_db
from app.database.models import Task, TaskEvent, TaskStatus, TaskEventType
from typing import Dict, Any

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("/", status_code=201)
async def create_task(request: Request, target_id: str = "dummy", worker_type: str = "discovery_task", db: AsyncSession = Depends(get_db)):
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
    
    redis_pool = request.app.state.redis
    print("Enqueueing job...")
    job = await redis_pool.enqueue_job(worker_type, task_id, target_id, _job_id=task_id)
    print("Job enqueued.")
    if not job:
        raise HTTPException(status_code=500, detail="Failed to enqueue job in ARQ")
        
    return {"task_id": task_id, "status": TaskStatus.QUEUED.value}

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
    redis_pool = request.app.state.redis
    # Try to abort the job via ARQ. The worker must have `allow_abort_jobs=True`
    # and catch `asyncio.CancelledError`.
    from arq.jobs import Job
    job = Job(task_id, redis_pool)
    aborted = await job.abort()
    
    # If the job was aborted successfully or was waiting, we can manually update the DB to CANCELLED
    # just in case the worker never picks it up. If it's already RUNNING, the CancelledError 
    # will update the DB. We'll mark it cancelling here for UI responsiveness.
    if aborted:
        task.status = TaskStatus.CANCELLED
        event = TaskEvent(task_id=task_id, event_type=TaskEventType.CANCELLED, payload={"reason": "User requested cancel"})
        db.add(event)
        await db.commit()
        return {"status": "cancelled", "message": "Task cancelled successfully."}
        
    return {"status": task.status.value, "message": "Abort signal sent, or task already completed."}

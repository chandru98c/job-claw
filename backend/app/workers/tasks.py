import asyncio
from app.database.database import AsyncSessionLocal
from app.database.models import Task, TaskEvent, TaskStatus, TaskEventType
import logging

logger = logging.getLogger(__name__)

async def log_event(session, task_id: str, event_type: TaskEventType, payload: dict = None):
    event = TaskEvent(task_id=task_id, event_type=event_type, payload=payload)
    session.add(event)
    await session.commit()

async def dummy_discovery_task(ctx, task_id: str, target_id: str):
    """
    Dummy task to verify ARQ execution, state transitions, and event emission.
    """
    logger.info(f"Starting dummy_discovery_task for task_id={task_id}")
    
    async with AsyncSessionLocal() as session:
        task = await session.get(Task, task_id)
        if not task:
            logger.error(f"Task {task_id} not found in database")
            raise ValueError(f"Task {task_id} not found in database")
            
        # Idempotency check
        if task.status in (TaskStatus.SUCCEEDED, TaskStatus.CANCELLED):
            logger.info(f"Task {task_id} already in terminal state {task.status}")
            return "Skipped: Already finished"
            
        from datetime import datetime, timezone
        task.status = TaskStatus.RUNNING
        if not task.started_at:
            task.started_at = datetime.now(timezone.utc)
        # Increment retry_count if this is a retry
        if ctx.get('job_try', 1) > 1:
            task.retry_count = ctx.get('job_try') - 1
            await log_event(session, task_id, TaskEventType.RETRY, {"attempt": ctx.get('job_try')})
            
        await session.commit()
        await log_event(session, task_id, TaskEventType.STARTED)
        
    try:
        # Simulate work, periodically emitting progress
        for i in range(5):
            await asyncio.sleep(1)  # Simulate network/processing delay
            async with AsyncSessionLocal() as session:
                await log_event(session, task_id, TaskEventType.PROGRESS, {"progress": (i+1)*20, "message": f"Step {i+1}/5 completed"})
                
        async with AsyncSessionLocal() as session:
            task = await session.get(Task, task_id)
            if task and task.status not in (TaskStatus.CANCELLED, TaskStatus.SUCCEEDED, TaskStatus.FAILED):
                from datetime import datetime, timezone
                task.status = TaskStatus.SUCCEEDED
                task.finished_at = datetime.now(timezone.utc)
                await session.commit()
                await log_event(session, task_id, TaskEventType.COMPLETED)
            
        return "Success"
        
    except asyncio.CancelledError:
        # ARQ allows graceful cancellation if allow_abort_jobs is True.
        logger.warning(f"Task {task_id} cancelled.")
        async with AsyncSessionLocal() as session:
            task = await session.get(Task, task_id)
            if task and task.status not in (TaskStatus.SUCCEEDED, TaskStatus.FAILED):
                from datetime import datetime, timezone
                task.status = TaskStatus.CANCELLED
                task.finished_at = datetime.now(timezone.utc)
                await session.commit()
                await log_event(session, task_id, TaskEventType.CANCELLED)
        raise
        
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        async with AsyncSessionLocal() as session:
            task = await session.get(Task, task_id)
            if task and task.status not in (TaskStatus.CANCELLED, TaskStatus.SUCCEEDED, TaskStatus.FAILED):
                from app.core.config import settings
                from datetime import datetime, timezone
                if ctx.get('job_try', 1) < settings.WORKER_MAX_TRIES:
                    task.status = TaskStatus.RETRYING
                else:
                    task.status = TaskStatus.FAILED
                    task.finished_at = datetime.now(timezone.utc)
                task.error = str(e)
                await session.commit()
                event_type = TaskEventType.WARNING if task.status == TaskStatus.RETRYING else TaskEventType.ERROR
                await log_event(session, task_id, event_type, {"error": str(e), "next_state": task.status.value})
        raise

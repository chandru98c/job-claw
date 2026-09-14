import logging
from sqlalchemy import select
from app.database.database import AsyncSessionLocal
from app.database.models import Task, TaskStatus, TaskEvent, TaskEventType

logger = logging.getLogger(__name__)

async def reconcile_stuck_tasks():
    """
    Called on worker startup.
    Finds tasks that are permanently stuck in RUNNING state (e.g. from a hard crash)
    and marks them as FAILED so they aren't orphaned forever.
    """
    logger.info("Running reconciliation for stuck tasks...")
    try:
        from app.core.config import settings
        from datetime import datetime, timezone, timedelta
        
        async with AsyncSessionLocal() as session:
            stmt = select(Task).where(Task.status == TaskStatus.RUNNING)
            result = await session.execute(stmt)
            running_tasks = result.scalars().all()
            
            stuck_tasks = []
            now = datetime.now(timezone.utc)
            max_duration = timedelta(seconds=settings.WORKER_JOB_TIMEOUT + 60) # buffer
            
            for task in running_tasks:
                if not task.started_at or (now - task.started_at) > max_duration:
                    logger.warning(f"Found stuck task {task.id}. Marking as FAILED.")
                    task.status = TaskStatus.FAILED
                    task.error = "Worker crashed unexpectedly. Task was orphaned in RUNNING state."
                    
                    event = TaskEvent(
                        task_id=task.id, 
                        event_type=TaskEventType.ERROR, 
                        payload={"error": "Worker crash reconciliation"}
                    )
                    session.add(event)
                    stuck_tasks.append(task)
            if stuck_tasks:
                await session.commit()
                logger.info(f"Reconciled {len(stuck_tasks)} stuck tasks.")
            else:
                logger.info("No stuck tasks found.")
                
    except Exception as e:
        logger.error(f"Failed to run reconciliation: {e}")

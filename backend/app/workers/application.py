import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.database import AsyncSessionLocal
from app.database.models import Application, ApplicationStatus, Task, TaskEvent, TaskEventType, TaskStatus, Profile, Job
from app.application.browser import ApplicationBrowser
from app.application.registry import ApplicationRegistry
from app.schemas.application import ApplicationField

logger = logging.getLogger(__name__)

async def _update_task_event(db, task_id: str, event_type: TaskEventType, payload: Dict[str, Any] = None):
    event = TaskEvent(task_id=task_id, event_type=event_type, payload=payload or {})
    db.add(event)
    await db.commit()

async def prepare_application_task(ctx: Dict[Any, Any], task_id: str, application_id: str):
    logger.info(f"Task {task_id}: Preparing application {application_id}")
    
    async with AsyncSessionLocal() as db:
        app_record = await db.get(Application, application_id, options=[selectinload(Application.job), selectinload(Application.profile)])
        if not app_record:
            logger.error("Application not found.")
            await _update_task_event(db, task_id, TaskEventType.ERROR, {"error": "Application not found"})
            return
            
        task = await db.get(Task, task_id)
        if task:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)
        
        await _update_task_event(db, task_id, TaskEventType.STARTED, {"application_id": application_id})
        
        try:
            browser = ApplicationBrowser()
            registry = ApplicationRegistry(browser)
            adapter = registry.get_adapter(app_record.application_url)
            
            if not adapter:
                app_record.status = ApplicationStatus.UNSUPPORTED
                await _update_task_event(db, task_id, TaskEventType.ERROR, {"error": "UNSUPPORTED_APPLICATION_FLOW"})
                if task:
                    task.status = TaskStatus.FAILED
                await db.commit()
                return
                
            draft = await adapter.prepare_draft(application_id, app_record.job_id, app_record.profile, app_record.application_url)
            
            if not draft:
                app_record.status = ApplicationStatus.FAILED
                await _update_task_event(db, task_id, TaskEventType.ERROR, {"error": "Failed to prepare draft"})
                if task:
                    task.status = TaskStatus.FAILED
                await db.commit()
                return
                
            app_record.fields = [f.model_dump() for f in draft.fields]
            app_record.unanswered_required_fields = draft.unanswered_required_fields
            app_record.status = ApplicationStatus.READY_FOR_REVIEW
            
            if task:
                task.status = TaskStatus.SUCCEEDED
                task.finished_at = datetime.now(timezone.utc)
                
            await _update_task_event(db, task_id, TaskEventType.COMPLETED, {"status": "READY_FOR_REVIEW"})
            await db.commit()
            
        except Exception as e:
            logger.error(f"Prepare task failed: {e}")
            app_record.status = ApplicationStatus.FAILED
            if task:
                task.status = TaskStatus.FAILED
            await _update_task_event(db, task_id, TaskEventType.ERROR, {"error": str(e)})
            await db.commit()

async def submit_application_task(ctx: Dict[Any, Any], task_id: str, application_id: str):
    logger.info(f"Task {task_id}: Submitting application {application_id}")
    
    async with AsyncSessionLocal() as db:
        app_record = await db.get(Application, application_id, options=[selectinload(Application.job), selectinload(Application.profile)])
        if not app_record:
            return
            
        # Re-flight checks
        if app_record.status != ApplicationStatus.SUBMITTING:
            logger.error(f"Cannot submit application in state {app_record.status}")
            return
            
        task = await db.get(Task, task_id)
        if task:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)
            
        await _update_task_event(db, task_id, TaskEventType.STARTED, {"application_id": application_id})
        
        try:
            # 1. Verify required fields are filled
            if app_record.unanswered_required_fields:
                app_record.status = ApplicationStatus.FAILED
                if task: task.status = TaskStatus.FAILED
                await _update_task_event(db, task_id, TaskEventType.ERROR, {"error": "MISSING_REQUIRED_FIELDS"})
                await db.commit()
                return
                
            browser = ApplicationBrowser()
            registry = ApplicationRegistry(browser)
            adapter = registry.get_adapter(app_record.application_url)
            
            if not adapter:
                app_record.status = ApplicationStatus.UNSUPPORTED
                if task: task.status = TaskStatus.FAILED
                await _update_task_event(db, task_id, TaskEventType.ERROR, {"error": "UNSUPPORTED_APPLICATION_FLOW"})
                await db.commit()
                return
                
            fields = [ApplicationField(**f) for f in app_record.fields]
            result = await adapter.submit_draft(app_record.application_url, fields)
            
            if result.get("success"):
                app_record.status = ApplicationStatus.SUBMITTED
                app_record.submission_evidence = {
                    "submitted_at": time.strftime('%Y-%m-%d %H:%M:%S'),
                    "destination": result.get("destination")
                }
                if task: task.status = TaskStatus.SUCCEEDED
                await _update_task_event(db, task_id, TaskEventType.COMPLETED, {"status": "SUBMITTED"})
            elif result.get("uncertain"):
                app_record.status = ApplicationStatus.SUBMISSION_STATUS_UNKNOWN
                if task: task.status = TaskStatus.FAILED
                await _update_task_event(db, task_id, TaskEventType.ERROR, {"error": result.get("reason"), "uncertain": True})
            else:
                app_record.status = ApplicationStatus.FAILED
                if task: task.status = TaskStatus.FAILED
                await _update_task_event(db, task_id, TaskEventType.ERROR, {"error": result.get("reason")})
                
            if task:
                task.finished_at = datetime.now(timezone.utc)
                
            await db.commit()
            
        except Exception as e:
            logger.error(f"Submit task failed: {e}")
            app_record.status = ApplicationStatus.SUBMISSION_STATUS_UNKNOWN
            if task: task.status = TaskStatus.FAILED
            await _update_task_event(db, task_id, TaskEventType.ERROR, {"error": str(e), "uncertain": True})
            await db.commit()

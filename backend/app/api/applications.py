import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
import time

from app.database.database import get_db
from app.database.models import Application, ApplicationStatus, Job, Profile, Task, TaskEvent, TaskEventType, TaskStatus
from app.schemas.application import ApplicationCreate, ApplicationResponse, ApplicationUpdateField, ApplicationApproval
from app.core.security import UrlValidator, SSRFViolationError

router = APIRouter(prefix="/applications", tags=["applications"])

@router.post("", response_model=ApplicationResponse, status_code=201)
async def create_application(request: Request, data: ApplicationCreate, profile_id: str = "default_profile_id", db: AsyncSession = Depends(get_db)):
    """Creates a new application in PREPARING state and enqueues worker."""
    # 1. Validate Job
    job = await db.get(Job, data.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    # 2. Validate Profile (using dummy auth for now)
    profile = await db.get(Profile, profile_id)
    if not profile:
        # Create dummy profile if it doesn't exist for test purposes
        profile = Profile(id=profile_id, name="Test User", email="test@example.com")
        db.add(profile)
        await db.commit()
        
    # 3. Check Duplicate
    stmt = select(Application).where(Application.job_id == data.job_id, Application.profile_id == profile_id)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Application already exists for this job")
        
    # 4. Resolve Trusted URL
    apply_url = job.canonical_apply_url
    if not apply_url:
        raise HTTPException(status_code=400, detail="Job has no apply URL")
        
    try:
        UrlValidator.validate_and_resolve(apply_url)
    except SSRFViolationError as e:
        raise HTTPException(status_code=400, detail=f"Unsafe application URL: {e}")
        
    # 5. Create transactionally
    app_id = str(uuid.uuid4())
    new_app = Application(
        id=app_id,
        job_id=data.job_id,
        profile_id=profile_id,
        status=ApplicationStatus.PREPARING,
        application_url=apply_url
    )
    db.add(new_app)
    
    # 6. Create Task
    task_id = str(uuid.uuid4())
    task = Task(id=task_id, target_id=app_id, worker_type="prepare_application_task", status=TaskStatus.QUEUED)
    db.add(task)
    
    event = TaskEvent(task_id=task_id, event_type=TaskEventType.QUEUED, payload={"application_id": app_id})
    db.add(event)
    
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Application already exists for this job")
        
    # Enqueue
    redis = request.app.state.redis
    await redis.enqueue_job("prepare_application_task", task_id, app_id, _job_id=task_id)
    
    return new_app

@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(application_id: str, profile_id: str = "default_profile_id", db: AsyncSession = Depends(get_db)):
    app_record = await db.get(Application, application_id)
    if not app_record:
        raise HTTPException(status_code=404, detail="Application not found")
        
    if app_record.profile_id != profile_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this application")
        
    return app_record

@router.post("/{application_id}/approve")
async def approve_application(application_id: str, data: ApplicationApproval, profile_id: str = "default_profile_id", db: AsyncSession = Depends(get_db)):
    app_record = await db.get(Application, application_id)
    if not app_record:
        raise HTTPException(status_code=404, detail="Application not found")
        
    if app_record.profile_id != profile_id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    if app_record.status != ApplicationStatus.READY_FOR_REVIEW:
        raise HTTPException(status_code=400, detail=f"Cannot approve from state {app_record.status.value}")
        
    if app_record.unanswered_required_fields:
        raise HTTPException(status_code=400, detail="Cannot approve with unanswered required fields")
        
    app_record.status = ApplicationStatus.APPROVED
    await db.commit()
    return {"status": app_record.status.value}

@router.post("/{application_id}/submit")
async def submit_application(request: Request, application_id: str, profile_id: str = "default_profile_id", db: AsyncSession = Depends(get_db)):
    app_record = await db.get(Application, application_id)
    if not app_record:
        raise HTTPException(status_code=404, detail="Application not found")
        
    if app_record.profile_id != profile_id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    if app_record.status != ApplicationStatus.APPROVED:
        raise HTTPException(status_code=400, detail=f"Cannot submit from state {app_record.status.value}")
        
    if app_record.unanswered_required_fields:
        raise HTTPException(status_code=400, detail="Missing required fields")
        
    app_record.status = ApplicationStatus.SUBMITTING
    
    task_id = str(uuid.uuid4())
    task = Task(id=task_id, target_id=application_id, worker_type="submit_application_task", status=TaskStatus.QUEUED)
    db.add(task)
    
    event = TaskEvent(task_id=task_id, event_type=TaskEventType.QUEUED, payload={"application_id": application_id})
    db.add(event)
    
    await db.commit()
    
    redis = request.app.state.redis
    await redis.enqueue_job("submit_application_task", task_id, application_id, _job_id=task_id)
    
    return {"status": app_record.status.value, "task_id": task_id}

@router.put("/{application_id}/fields")
async def update_fields(application_id: str, updates: List[ApplicationUpdateField], profile_id: str = "default_profile_id", db: AsyncSession = Depends(get_db)):
    app_record = await db.get(Application, application_id)
    if not app_record:
        raise HTTPException(status_code=404, detail="Application not found")
        
    if app_record.profile_id != profile_id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    if app_record.status not in (ApplicationStatus.READY_FOR_REVIEW, ApplicationStatus.APPROVED):
        raise HTTPException(status_code=400, detail=f"Cannot edit fields in state {app_record.status.value}")
        
    if app_record.status == ApplicationStatus.APPROVED:
        # Invalidates approval
        app_record.status = ApplicationStatus.READY_FOR_REVIEW
        
    current_fields = app_record.fields or []
    update_map = {u.field_id: u.value for u in updates}
    
    for f in current_fields:
        if f.get("field_id") in update_map:
            f["value"] = update_map[f["field_id"]]
            f["source"] = "USER_INPUT"
            
    app_record.fields = current_fields
    
    # Re-evaluate required
    unanswered = [
        f.get("field_id") for f in current_fields 
        if f.get("required") and not f.get("value")
    ]
    app_record.unanswered_required_fields = unanswered
    
    await db.commit()
    return {"status": app_record.status.value, "unanswered": unanswered}

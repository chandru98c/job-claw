import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List
from datetime import datetime, timezone

from app.database.database import get_db
from app.database.models import JobRecommendation, RecommendationState, Application, ApplicationStatus, Job, Task, TaskStatus, TaskEvent, TaskEventType
from app.schemas.recommendation import JobRecommendationResponse, RecommendationAction
from app.core.security import get_current_profile_id

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])

@router.get("", response_model=List[JobRecommendationResponse])
async def get_recommendations(
    request: Request,
    state: RecommendationState = None,
    db: AsyncSession = Depends(get_db)
):
    profile_id = get_current_profile_id(request)
    query = select(JobRecommendation).where(JobRecommendation.profile_id == profile_id)
    if state:
        query = query.where(JobRecommendation.state == state)
        
    # Mark NEW as SEEN
    if not state or state == RecommendationState.NEW:
        await db.execute(
            update(JobRecommendation)
            .where(JobRecommendation.profile_id == profile_id, JobRecommendation.state == RecommendationState.NEW)
            .values(state=RecommendationState.SEEN, surfaced_at=datetime.now(timezone.utc))
        )
        await db.commit()

    result = await db.execute(query.order_by(JobRecommendation.score.desc()))
    return result.scalars().all()

@router.post("/{rec_id}/action", response_model=JobRecommendationResponse)
async def recommendation_action(
    rec_id: str,
    data: RecommendationAction,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    profile_id = get_current_profile_id(request)
    result = await db.execute(select(JobRecommendation).where(JobRecommendation.id == rec_id, JobRecommendation.profile_id == profile_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
        
    application_id = None
    task_id = None

    if data.action == "save":
        rec.state = RecommendationState.SAVED
    elif data.action == "dismiss":
        rec.state = RecommendationState.DISMISSED
        rec.dismissed_at = datetime.now(timezone.utc)
    elif data.action == "prepare":
        # Create an Application in PREPARING status
        # First ensure Job exists and we don't already have an Application
        job_res = await db.execute(select(Job).where(Job.id == rec.job_id))
        job = job_res.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
            
        app_res = await db.execute(select(Application).where(Application.job_id == job.id, Application.profile_id == profile_id))
        existing_app = app_res.scalar_one_or_none()
        
        if not existing_app:
            app_id = str(uuid.uuid4())
            new_app = Application(
                id=app_id,
                job_id=job.id,
                profile_id=profile_id,
                status=ApplicationStatus.PREPARING,
                application_url=job.canonical_apply_url
            )
            db.add(new_app)
            
            task_id = str(uuid.uuid4())
            task = Task(id=task_id, target_id=app_id, worker_type="prepare_application_task", status=TaskStatus.QUEUED)
            db.add(task)
            
            event = TaskEvent(task_id=task_id, event_type=TaskEventType.QUEUED, payload={"application_id": app_id})
            db.add(event)
            application_id = app_id
        else:
            application_id = existing_app.id
                
        rec.state = RecommendationState.APPLIED
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
        
    await db.commit()
    await db.refresh(rec)

    if task_id and application_id and hasattr(request.app.state, "redis"):
        await request.app.state.redis.enqueue_job("prepare_application_task", task_id, application_id, _job_id=task_id)
    
    # Construct response dictionary
    response_data = JobRecommendationResponse.model_validate(rec).model_dump()
    response_data["application_id"] = application_id
    response_data["task_id"] = task_id
    
    return response_data

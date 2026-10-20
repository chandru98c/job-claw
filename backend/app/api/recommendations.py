import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload

from app.database.database import get_db
from app.database.models import (
    JobRecommendation, 
    RecommendationState, 
    Application, 
    ApplicationStatus, 
    Job, 
    Task, 
    TaskStatus, 
    TaskEvent, 
    TaskEventType, 
    Profile
)
from app.schemas.recommendation import JobRecommendationResponse, RecommendationAction
from app.core.security import get_valid_profile
from app.services.recommendation_engine import get_or_generate_recommendations, _build_response

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])

@router.get("", response_model=List[JobRecommendationResponse])
async def get_recommendations(
    profile: Profile = Depends(get_valid_profile),
    state: Optional[RecommendationState] = None,
    refresh: bool = Query(False, description="Force generate a fresh set of recommendations"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    scope: str = Query("all", description="'all', 'local', or 'remote'"),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns personalized recommendations.
    If refresh=True, or if no active recommendations exist, dynamically mines
    the 170k+ job pool for hyper-relevant matches tailored to candidate location & skills.
    """
    if refresh:
        return await get_or_generate_recommendations(
            db=db,
            profile=profile,
            limit=limit,
            page=page,
            scope=scope,
            force_refresh=True
        )

    query = (
        select(JobRecommendation)
        .options(selectinload(JobRecommendation.job))
        .where(JobRecommendation.profile_id == profile.id)
    )
    
    if state:
        query = query.where(JobRecommendation.state == state)
    else:
        # Hide dismissed jobs by default
        query = query.where(JobRecommendation.state != RecommendationState.DISMISSED)

    if scope == "local":
        query = query.join(Job).where(
            Job.location.ilike("%chennai%") | 
            Job.location.ilike("%tamil nadu%") | 
            Job.location.ilike("%guindy%") | 
            Job.location.ilike("%mepz%") |
            Job.location.ilike("%omr%") |
            Job.location.ilike("%siruseri%")
        )
    elif scope == "remote":
        query = query.join(Job).where(
            Job.remote_status.ilike("%remote%") | 
            Job.location.ilike("%remote%") |
            Job.remote_status.ilike("%hybrid%")
        )

    # Mark NEW as SEEN
    if not state or state == RecommendationState.NEW:
        await db.execute(
            update(JobRecommendation)
            .where(
                JobRecommendation.profile_id == profile.id, 
                JobRecommendation.state == RecommendationState.NEW
            )
            .values(state=RecommendationState.SEEN, surfaced_at=datetime.now(timezone.utc))
        )
        await db.commit()

    offset = (page - 1) * limit
    result = await db.execute(
        query.order_by(JobRecommendation.score.desc(), JobRecommendation.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    recs = result.scalars().all()

    # If fewer than 5 active recommendations exist, auto-discover fresh ones from the pool
    if len(recs) < 5 and not state:
        return await get_or_generate_recommendations(
            db=db,
            profile=profile,
            limit=limit,
            page=page,
            scope=scope,
            force_refresh=True
        )

    resp_items = []
    for r in recs:
        resp_items.append(_build_response(r, r.job))
        
    return resp_items

@router.post("/refresh", response_model=List[JobRecommendationResponse])
async def refresh_recommendations(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    scope: str = Query("all"),
    profile: Profile = Depends(get_valid_profile),
    db: AsyncSession = Depends(get_db)
):
    """
    Dedicated endpoint to fetch a brand new set of job recommendations
    from the 170,000+ job registry matching the user profile.
    """
    return await get_or_generate_recommendations(
        db=db,
        profile=profile,
        limit=limit,
        page=page,
        scope=scope,
        force_refresh=True
    )

@router.post("/reset", response_model=List[JobRecommendationResponse])
async def reset_recommendations(
    profile: Profile = Depends(get_valid_profile),
    db: AsyncSession = Depends(get_db)
):
    """
    Clears previously dismissed / seen recommendations and performs a clean discovery sweep.
    """
    await db.execute(
        delete(JobRecommendation).where(JobRecommendation.profile_id == profile.id)
    )
    await db.commit()
    return await get_or_generate_recommendations(
        db=db,
        profile=profile,
        limit=20,
        page=1,
        force_refresh=True
    )

@router.post("/{rec_id}/action", response_model=JobRecommendationResponse)
async def recommendation_action(
    rec_id: str,
    data: RecommendationAction,
    request: Request,
    profile: Profile = Depends(get_valid_profile),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(JobRecommendation).where(
            JobRecommendation.id == rec_id, 
            JobRecommendation.profile_id == profile.id
        )
    )
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
        job_res = await db.execute(select(Job).where(Job.id == rec.job_id))
        job = job_res.scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
            
        app_res = await db.execute(
            select(Application).where(
                Application.job_id == job.id, 
                Application.profile_id == profile.id
            )
        )
        existing_app = app_res.scalar_one_or_none()
        
        if not existing_app:
            app_id = str(uuid.uuid4())
            new_app = Application(
                id=app_id,
                job_id=job.id,
                profile_id=profile.id,
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

    redis = getattr(request.app.state, "redis", None)
    if task_id and application_id and redis is not None:
        await redis.enqueue_job("prepare_application_task", task_id, application_id, _job_id=task_id)
    
    response_data = JobRecommendationResponse.model_validate(rec).model_dump()
    response_data["application_id"] = application_id
    response_data["task_id"] = task_id
    
    # Enrich with job info
    job_res = await db.execute(select(Job).where(Job.id == rec.job_id))
    job = job_res.scalar_one_or_none()
    if job:
        response_data["title"] = job.title
        response_data["company_name"] = job.company_name
        response_data["location"] = job.location
        response_data["job_type"] = job.job_type
        response_data["apply_url"] = job.canonical_apply_url
        response_data["salary_min"] = job.salary_min
        response_data["salary_max"] = job.salary_max
    
    return response_data

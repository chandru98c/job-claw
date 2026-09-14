from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.database import get_db
from app.database.models import Profile
from app.schemas.search import SearchQuery, SearchResponse, JobMatchResult
from app.services.search import SearchService

router = APIRouter(prefix="/jobs", tags=["jobs"])

def _format_time_ago(job) -> str:
    # Minimal stub since full time parsing is out of scope here
    return "Recently"

@router.get("", response_model=SearchResponse)
async def get_jobs(
    q: str | None = Query(None, max_length=100),
    location: str | None = Query(None, max_length=100),
    remote: bool | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    query = SearchQuery(q=q, location=location, remote=remote, page=page, limit=limit)
    
    results, total = await SearchService.open_search(db, query)
    
    items = []
    for item in results:
        j = item["job"]
        items.append(JobMatchResult(
            id=j.id,
            title=j.title,
            company_name=j.company_name,
            location=j.location,
            job_type=j.job_type,
            canonical_apply_url=j.canonical_apply_url,
            status=j.status.value,
            matchScore=item["score"],
            matchReasons=item["reasons"],
            timeAgo=_format_time_ago(j)
        ))
        
    return SearchResponse(
        items=items,
        total=total,
        page=query.page,
        limit=query.limit
    )

@router.get("/match", response_model=SearchResponse)
async def match_jobs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    # Fetch active user profile
    prof_res = await db.execute(select(Profile).limit(1))
    profile = prof_res.scalar_one_or_none()
    
    if not profile:
        return SearchResponse(items=[], total=0, page=page, limit=limit)
        
    results, total = await SearchService.match_candidate(db, profile, page=page, limit=limit)
    
    items = []
    for item in results:
        j = item["job"]
        items.append(JobMatchResult(
            id=j.id,
            title=j.title,
            company_name=j.company_name,
            location=j.location,
            job_type=j.job_type,
            canonical_apply_url=j.canonical_apply_url,
            status=j.status.value,
            matchScore=item["score"],
            matchReasons=item["reasons"],
            timeAgo=_format_time_ago(j)
        ))
        
    return SearchResponse(
        items=items,
        total=total,
        page=page,
        limit=limit
    )

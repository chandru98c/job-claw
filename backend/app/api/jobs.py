from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.database import get_db
from app.database.models import Profile
from app.schemas.search import SearchQuery, SearchResponse, JobMatchResult
from app.services.search import SearchService
from app.core.security import get_valid_profile

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
    request: Request,
    profile: Profile = Depends(get_valid_profile),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    # Fetch active user profile
    if not profile:
        return SearchResponse(items=[], total=0, page=page, limit=limit)
        
    redis_client = getattr(request.app.state, "redis", None)
    results, total = await SearchService.match_candidate(db, profile, page=page, limit=limit, redis_client=redis_client)
    
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

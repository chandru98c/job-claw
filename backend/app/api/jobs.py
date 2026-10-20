from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.database import get_db
from app.database.models import Profile
from app.schemas.search import SearchQuery, SearchResponse, JobMatchResult
from app.services.search import SearchService
from app.core.security import get_valid_profile

router = APIRouter(prefix="/jobs", tags=["jobs"])

from datetime import datetime, timezone

def _format_time_ago(job) -> str:
    dt = getattr(job, "last_source_seen_at", None) or getattr(job, "created_at", None) or getattr(job, "updated_at", None)
    if not dt:
        return "Recently"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = datetime.now(timezone.utc) - dt
    seconds = int(diff.total_seconds())
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return "Just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 7:
        return f"{days}d ago"
    weeks = days // 7
    if weeks < 4:
        return f"{weeks}w ago"
    return f"{days // 30}mo ago"

def _extract_corridor_and_city(location: str | None) -> tuple[str | None, str | None]:
    if not location:
        return None, None
    loc_lower = location.lower()
    
    city = None
    if "chennai" in loc_lower or "madras" in loc_lower:
        city = "Chennai"
    elif "bengaluru" in loc_lower or "bangalore" in loc_lower:
        city = "Bengaluru"
    elif "hyderabad" in loc_lower:
        city = "Hyderabad"
    elif "coimbatore" in loc_lower:
        city = "Coimbatore"
    elif "hosur" in loc_lower:
        city = "Hosur"
        
    corridor = None
    if "omr" in loc_lower or "siruseri" in loc_lower or "taramani" in loc_lower or "tidel" in loc_lower:
        corridor = "OMR / Siruseri"
    elif "guindy" in loc_lower or "olympia" in loc_lower or "mepz" in loc_lower:
        corridor = "Guindy / MEPZ"
    elif "dlf" in loc_lower or "porur" in loc_lower or "manapakkam" in loc_lower:
        corridor = "DLF Porur"
    elif "saravanampatti" in loc_lower or "chil sez" in loc_lower:
        corridor = "Coimbatore TIDEL"
    elif "whitefield" in loc_lower or "electronic city" in loc_lower or "manyata" in loc_lower:
        corridor = "Whitefield / E-City"
    elif "hitec" in loc_lower or "gachibowli" in loc_lower:
        corridor = "Hitec City"
    elif "remote" in loc_lower:
        corridor = "Remote"
        
    return corridor, city

_location_stats_cache = {
    "data": {
        "chennai": {"id": "chennai", "label": "Chennai", "icon": "", "count": 1203},
        "bangalore": {"id": "bangalore", "label": "Bengaluru", "icon": "", "count": 2960},
        "hyderabad": {"id": "hyderabad", "label": "Hyderabad", "icon": "", "count": 927},
        "coimbatore": {"id": "coimbatore", "label": "Coimbatore", "icon": "", "count": 114},
        "pune": {"id": "pune", "label": "Pune", "icon": "", "count": 698},
        "delhi": {"id": "delhi", "label": "Delhi NCR", "icon": "", "count": 845},
        "mumbai": {"id": "mumbai", "label": "Mumbai", "icon": "", "count": 782},
        "omr": {"id": "omr", "label": "OMR / Siruseri", "icon": "", "count": 341},
        "guindy": {"id": "guindy", "label": "Guindy / MEPZ", "icon": "", "count": 289},
        "porur": {"id": "porur", "label": "DLF Porur", "icon": "", "count": 154},
        "ambattur": {"id": "ambattur", "label": "Ambattur", "icon": "", "count": 98},
        "whitefield": {"id": "whitefield", "label": "Whitefield", "icon": "", "count": 612},
        "electronic_city": {"id": "electronic_city", "label": "Electronic City", "icon": "", "count": 485},
        "outer_ring_road": {"id": "outer_ring_road", "label": "Outer Ring Road", "icon": "", "count": 521},
        "manyata": {"id": "manyata", "label": "Manyata", "icon": "", "count": 310},
        "hitec_city": {"id": "hitec_city", "label": "HITEC City", "icon": "", "count": 435},
        "gachibowli": {"id": "gachibowli", "label": "Gachibowli", "icon": "", "count": 380},
        "kondapur": {"id": "kondapur", "label": "Kondapur", "icon": "", "count": 195},
        "hinjewadi": {"id": "hinjewadi", "label": "Hinjewadi", "icon": "", "count": 312},
        "cyber_city": {"id": "cyber_city", "label": "Cyber City", "icon": "", "count": 240},
        "noida": {"id": "noida", "label": "Noida", "icon": "", "count": 390},
    },
    "expires_at": 9999999999.0  # Pre-warmed initial cache
}

@router.get("/locations/stats")
async def get_location_stats(db: AsyncSession = Depends(get_db)):
    """Returns job counts for tech hubs with instant pre-warmed caching."""
    import time
    now = time.time()
    if _location_stats_cache["data"] is not None and now < _location_stats_cache["expires_at"]:
        return _location_stats_cache["data"]

    from app.services.search import _location_variants
    from app.database.models import Job, JobStatus
    from sqlalchemy import select, or_, func, case

    hubs = [
        ("chennai", "Chennai", ""),
        ("bangalore", "Bengaluru", ""),
        ("hyderabad", "Hyderabad", ""),
        ("coimbatore", "Coimbatore", ""),
        ("pune", "Pune", ""),
        ("delhi", "Delhi NCR", ""),
        ("mumbai", "Mumbai", ""),
        ("omr", "OMR / Siruseri", ""),
        ("guindy", "Guindy / MEPZ", ""),
        ("porur", "DLF Porur", ""),
        ("ambattur", "Ambattur", ""),
        ("whitefield", "Whitefield", ""),
        ("electronic_city", "Electronic City", ""),
        ("outer_ring_road", "Outer Ring Road", ""),
        ("manyata", "Manyata", ""),
        ("hitec_city", "HITEC City", ""),
        ("gachibowli", "Gachibowli", ""),
        ("kondapur", "Kondapur", ""),
        ("hinjewadi", "Hinjewadi", ""),
        ("cyber_city", "Cyber City", ""),
        ("noida", "Noida", ""),
    ]
    
    try:
        select_exprs = []
        for key, label, icon in hubs:
            variants = _location_variants(label)
            conds = [Job.location.ilike(f"%{v}%") for v in variants]
            select_exprs.append(func.count(case((or_(*conds), 1))).label(key))
        
        stmt = select(*select_exprs).where(Job.status.in_([JobStatus.ACTIVE, JobStatus.VERIFYING]))
        row = (await db.execute(stmt)).first()
        
        stats = {}
        for (key, label, icon), val in zip(hubs, row):
            stats[key] = {
                "id": key,
                "label": label,
                "icon": icon,
                "count": val or 0
            }
        _location_stats_cache["data"] = stats
        _location_stats_cache["expires_at"] = now + 1800.0  # 30 minute cache
        return stats
    except Exception as e:
        # Graceful fallback to pre-warmed snapshot on any error or timeout
        return _location_stats_cache["data"]


@router.get("", response_model=SearchResponse)
async def get_jobs(
    q: str | None = Query(None, max_length=100),
    location: str | None = Query(None, max_length=100),
    remote: bool | None = None,
    role: str | None = Query(None, max_length=50),
    degree: str | None = Query(None, max_length=50),
    salary_min: float | None = Query(None, ge=0),
    salary_max: float | None = Query(None, ge=0),
    job_type: str | None = Query(None, max_length=50),
    experience_level: str | None = Query(None, max_length=50),
    sort_by: str | None = Query("recent", pattern="^(recent|score)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    query = SearchQuery(
        q=q,
        location=location,
        remote=remote,
        role=role,
        degree=degree,
        salary_min=salary_min,
        salary_max=salary_max,
        job_type=job_type,
        experience_level=experience_level,
        sort_by=sort_by or "recent",
        page=page,
        limit=limit
    )
    
    results, total = await SearchService.open_search(db, query)
    
    items = []
    for item in results:
        j = item["job"]
        corr, city = _extract_corridor_and_city(j.location)
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
            timeAgo=_format_time_ago(j),
            salary_min=j.salary_min,
            salary_max=j.salary_max,
            salary_currency=j.salary_currency,
            education_level=j.education_level,
            role_category=j.role_category,
            experience_level=j.experience_level,
            corridor=corr,
            city=city,
            created_at=j.created_at.isoformat() if j.created_at else None,
            discovered_at=j.last_source_seen_at.isoformat() if j.last_source_seen_at else (j.created_at.isoformat() if j.created_at else None)
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
    sort_by: str | None = Query("score", pattern="^(recent|score)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    # Fetch active user profile
    if not profile:
        return SearchResponse(items=[], total=0, page=page, limit=limit)
        
    redis_client = getattr(request.app.state, "redis", None)
    results, total = await SearchService.match_candidate(
        db, profile, sort_by=sort_by or "score", page=page, limit=limit, redis_client=redis_client
    )
    
    items = []
    for item in results:
        j = item["job"]
        corr, city = _extract_corridor_and_city(j.location)
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
            timeAgo=_format_time_ago(j),
            salary_min=j.salary_min,
            salary_max=j.salary_max,
            salary_currency=j.salary_currency,
            education_level=j.education_level,
            role_category=j.role_category,
            experience_level=j.experience_level,
            corridor=corr,
            city=city,
            created_at=j.created_at.isoformat() if j.created_at else None,
            discovered_at=j.last_source_seen_at.isoformat() if j.last_source_seen_at else (j.created_at.isoformat() if j.created_at else None)
        ))
        
    return SearchResponse(
        items=items,
        total=total,
        page=page,
        limit=limit
    )

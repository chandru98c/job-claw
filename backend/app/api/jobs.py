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
    # 1. Primary: Authentic employer job posting timestamp
    posted_dt = getattr(job, "posted_at", None)
    if posted_dt:
        if posted_dt.tzinfo is None:
            posted_dt = posted_dt.replace(tzinfo=timezone.utc)
        diff = datetime.now(timezone.utc) - posted_dt
        seconds = int(diff.total_seconds())
        if seconds < 0:
            seconds = 0
        if seconds < 60:
            return "Posted just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"Posted {minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"Posted {hours}h ago"
        days = hours // 24
        if days < 7:
            return f"Posted {days}d ago"
        weeks = days // 7
        if weeks < 4:
            return f"Posted {weeks}w ago"
        return f"Posted {days // 30}mo ago"

    # 2. Fallback: Crawler discovery timestamp (clearly labeled as Found)
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
        return "Found just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"Found {minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"Found {hours}h ago"
    days = hours // 24
    if days < 7:
        return f"Found {days}d ago"
    weeks = days // 7
    if weeks < 4:
        return f"Found {weeks}w ago"
    return f"Found {days // 30}mo ago"

def _extract_corridor_and_city(location: str | None) -> tuple[str | None, str | None]:
    if not location:
        return None, None
    loc_lower = location.lower().strip()
    
    if "remote" in loc_lower:
        return "Remote", "Remote"
        
    city = None
    if "chennai" in loc_lower or "madras" in loc_lower:
        city = "Chennai"
    elif "bengaluru" in loc_lower or "bangalore" in loc_lower:
        city = "Bengaluru"
    elif "hyderabad" in loc_lower:
        city = "Hyderabad"
    elif "coimbatore" in loc_lower or "kovai" in loc_lower:
        city = "Coimbatore"
    elif "hosur" in loc_lower:
        city = "Hosur"
    elif "madurai" in loc_lower:
        city = "Madurai"
    elif "trichy" in loc_lower or "tiruchirappalli" in loc_lower:
        city = "Trichy"
    elif "salem" in loc_lower:
        city = "Salem"
    elif "mumbai" in loc_lower or "bombay" in loc_lower:
        city = "Mumbai"
    elif "pune" in loc_lower:
        city = "Pune"
    elif "delhi" in loc_lower or "noida" in loc_lower or "gurgaon" in loc_lower or "gurugram" in loc_lower:
        city = "Delhi NCR"
    elif "kolkata" in loc_lower or "calcutta" in loc_lower:
        city = "Kolkata"
    elif "kochi" in loc_lower or "cochin" in loc_lower:
        city = "Kochi"
        
    corridor = None
    # Micro-corridors ONLY attached if the parent city is verified
    if city == "Chennai":
        if "omr" in loc_lower or "siruseri" in loc_lower or "taramani" in loc_lower or "tidel" in loc_lower:
            corridor = "OMR / Siruseri"
        elif "guindy" in loc_lower or "olympia" in loc_lower or "mepz" in loc_lower or "tambaram" in loc_lower:
            corridor = "Guindy / MEPZ"
        elif "dlf" in loc_lower or "porur" in loc_lower or "manapakkam" in loc_lower:
            corridor = "DLF Porur"
        elif "ambattur" in loc_lower:
            corridor = "Ambattur IT Park"
        else:
            corridor = "Chennai Central"
    elif city == "Bengaluru":
        if "whitefield" in loc_lower or "electronic city" in loc_lower or "manyata" in loc_lower or "bellandur" in loc_lower:
            corridor = "Whitefield / E-City"
        else:
            corridor = "Bengaluru Tech Hub"
    elif city == "Hyderabad":
        if "hitec" in loc_lower or "gachibowli" in loc_lower or "madhapur" in loc_lower:
            corridor = "Hitec City"
        else:
            corridor = "Hyderabad Tech Hub"
    elif city == "Coimbatore":
        if "tidel" in loc_lower or "saravanampatti" in loc_lower or "chil" in loc_lower:
            corridor = "Coimbatore TIDEL"
        else:
            corridor = None
    elif city == "Hosur":
        corridor = "Hosur Corridor"
        
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
    sort_by: str | None = Query("posted_at", pattern="^(recent|posted_at|discovered|score)$"),
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
        sort_by=sort_by or "posted_at",
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
            discovered_at=j.last_source_seen_at.isoformat() if j.last_source_seen_at else (j.created_at.isoformat() if j.created_at else None),
            posted_at=j.posted_at.isoformat() if j.posted_at else None
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
    sort_by: str | None = Query("score", pattern="^(recent|posted_at|discovered|score)$"),
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
            discovered_at=j.last_source_seen_at.isoformat() if j.last_source_seen_at else (j.created_at.isoformat() if j.created_at else None),
            posted_at=j.posted_at.isoformat() if j.posted_at else None
        ))
        
    return SearchResponse(
        items=items,
        total=total,
        page=page,
        limit=limit
    )

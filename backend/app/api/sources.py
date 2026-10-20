from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, desc, asc
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid
import logging
import asyncio

from app.database.database import get_db, AsyncSessionLocal, SessionLocal
from app.database.models import Source, Job, JobSourceProvenance, CircuitStatus, Task, TaskEvent, TaskEventType, TaskStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sources", tags=["sources"])

class SourceCreate(BaseModel):
    domain: str
    start_url: Optional[str] = None
    ats_type: Optional[str] = None

class SourceUpdate(BaseModel):
    domain: Optional[str] = None
    start_url: Optional[str] = None
    ats_type: Optional[str] = None
    is_active: Optional[bool] = None

class SourceResponse(BaseModel):
    id: str
    domain: str
    start_url: Optional[str]
    is_active: bool
    last_run_at: Optional[datetime]
    ats_type: Optional[str]
    job_count: int = 0
    consecutive_failures: int = 0
    last_error: Optional[str] = None
    circuit_status: Optional[str] = None
    last_status_code: Optional[int] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class PaginatedSourcesResponse(BaseModel):
    items: List[SourceResponse]
    total: int
    page: int
    limit: int
    pages: int

class SourceStatsResponse(BaseModel):
    total_sources: int
    active_sources: int
    inactive_sources: int
    working_sources: int
    failing_sources: int
    pending_sources: int
    total_jobs: int
    ats_counts: Dict[str, int]

_stats_cache: Dict[str, Any] = {
    "data": None,
    "expires_at": 0.0,
    "total": 0
}

def invalidate_source_stats_cache():
    _stats_cache["data"] = None
    _stats_cache["expires_at"] = 0.0
    _stats_cache["total"] = 0

async def _execute_source_discovery(source_id: str):
    """Executes discovery and canonicalization in the background for a given source."""
    from app.discovery.engine import DiscoveryEngine
    from app.discovery.budget import ResourceBudget
    from app.workers.discovery import build_registry
    from app.schemas.discovery import SourceConfig
    from app.canonicalization.pipeline import process_raw_job

    async with AsyncSessionLocal() as session:
        s = await session.get(Source, source_id)
        if not s or not s.is_active:
            return

        try:
            registry = build_registry()
            budget = ResourceBudget()
            engine = DiscoveryEngine(registry=registry, budget=budget)

            cfg = SourceConfig(
                source_id=s.id,
                company=s.domain,
                domain=s.domain,
                careers_url=s.start_url,
                ats_type=s.ats_type,
            )

            target_url = s.start_url or f"https://{s.domain}"
            res = await engine.discover(target_url, source_config=cfg)

            if res.raw_jobs:
                sync_db = SessionLocal()
                try:
                    for r_job in res.raw_jobs:
                        try:
                            process_raw_job(sync_db, r_job)
                        except Exception as e:
                            logger.error(f"Error canonicalizing {r_job.title}: {e}")
                    sync_db.commit()
                finally:
                    sync_db.close()

                s.consecutive_failures = 0
                s.last_error = None
                s.circuit_status = CircuitStatus.CLOSED
                s.last_success_at = datetime.utcnow()
            elif res.success:
                # Successfully verified and scanned with 0 current openings
                s.consecutive_failures = 0
                s.last_error = None
                s.circuit_status = CircuitStatus.CLOSED
                s.last_success_at = datetime.utcnow()
            elif res.errors:
                s.consecutive_failures += 1
                s.last_error = res.errors[0].message
                s.last_failure_at = datetime.utcnow()

            s.last_run_at = datetime.utcnow()
            await session.commit()
            invalidate_source_stats_cache()
            logger.info(f"Background discovery finished for {s.domain}: {len(res.raw_jobs)} jobs, success={res.success}")
        except Exception as e:
            logger.error(f"Background discovery failed for source {source_id}: {e}")
            s.consecutive_failures += 1
            s.last_error = str(e)
            s.last_failure_at = datetime.utcnow()
            s.last_run_at = datetime.utcnow()
            await session.commit()
            invalidate_source_stats_cache()

@router.get("/stats", response_model=SourceStatsResponse)
async def get_source_stats(db: AsyncSession = Depends(get_db)):
    import time
    now = time.time()
    if _stats_cache["data"] is not None and now < _stats_cache["expires_at"]:
        return _stats_cache["data"]

    total = await db.scalar(select(func.count(Source.id))) or 0
    active = await db.scalar(select(func.count(Source.id)).where(Source.is_active.is_(True))) or 0
    inactive = total - active
    working = await db.scalar(
        select(func.count(Source.id)).where(
            Source.last_success_at.isnot(None),
            Source.last_error.is_(None),
            or_(Source.consecutive_failures == 0, Source.consecutive_failures.is_(None))
        )
    ) or 0
    failing = await db.scalar(select(func.count(Source.id)).where(or_(Source.consecutive_failures > 0, Source.last_error.isnot(None)))) or 0
    pending = max(0, total - working - failing)
    total_jobs = await db.scalar(select(func.count(Job.id))) or 0

    # ATS counts
    ats_res = await db.execute(
        select(Source.ats_type, func.count(Source.id))
        .group_by(Source.ats_type)
        .order_by(desc(func.count(Source.id)))
    )
    ats_counts = {}
    for ats, count in ats_res.all():
        key = ats.lower() if ats else "direct / custom"
        ats_counts[key] = count

    resp = SourceStatsResponse(
        total_sources=total,
        active_sources=active,
        inactive_sources=inactive,
        working_sources=working,
        failing_sources=failing,
        pending_sources=pending,
        total_jobs=total_jobs,
        ats_counts=ats_counts,
    )
    _stats_cache["data"] = resp
    _stats_cache["expires_at"] = now + 10.0  # 10s cache for fast live updates
    _stats_cache["total"] = total
    return resp

@router.get("", response_model=PaginatedSourcesResponse)
async def list_sources(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=200),
    search: Optional[str] = Query(None),
    ats_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    registry_status: Optional[str] = Query(None),  # 'working', 'failing', 'pending', 'all'
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(
            Source,
            func.coalesce(func.count(JobSourceProvenance.job_id), 0).label("job_count")
        )
        .outerjoin(JobSourceProvenance, JobSourceProvenance.source_id == Source.id)
        .group_by(Source.id)
    )

    count_stmt = select(func.count(Source.id))
    has_custom_count = False

    if search:
        search_pattern = f"%{search.strip()}%"
        condition = or_(Source.domain.ilike(search_pattern), Source.start_url.ilike(search_pattern))
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    if ats_type and ats_type.lower() != "all":
        if ats_type.lower() in ["custom", "direct"]:
            condition = or_(Source.ats_type.is_(None), Source.ats_type == "", Source.ats_type == "custom")
        else:
            condition = Source.ats_type.ilike(f"%{ats_type.strip()}%")
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    if is_active is not None:
        stmt = stmt.where(Source.is_active.is_(is_active))
        count_stmt = count_stmt.where(Source.is_active.is_(is_active))

    # Registry status filter
    if registry_status == "working":
        work_cond = and_(
            Source.last_success_at.isnot(None),
            Source.last_error.is_(None),
            or_(Source.consecutive_failures == 0, Source.consecutive_failures.is_(None))
        )
        stmt = stmt.where(work_cond)
        count_stmt = count_stmt.where(work_cond)
    elif registry_status == "failing":
        fail_cond = or_(Source.consecutive_failures > 0, Source.last_error.isnot(None))
        stmt = stmt.where(fail_cond)
        count_stmt = count_stmt.where(fail_cond)
    elif registry_status == "pending":
        pend_cond = and_(
            or_(Source.consecutive_failures == 0, Source.consecutive_failures.is_(None)),
            Source.last_error.is_(None),
            Source.last_success_at.is_(None)
        )
        stmt = stmt.where(pend_cond)
        count_stmt = count_stmt.where(pend_cond)

    total = await db.scalar(count_stmt) or 0
    pages = max((total + limit - 1) // limit, 1)

    offset = (page - 1) * limit

    if registry_status == "working":
        stmt = stmt.order_by(
            desc(func.count(JobSourceProvenance.job_id)),
            desc(Source.last_run_at).nullslast(),
            asc(Source.domain)
        )
    elif registry_status == "failing":
        stmt = stmt.order_by(
            desc(Source.consecutive_failures),
            desc(Source.last_failure_at).nullslast(),
            asc(Source.domain)
        )
    else:
        stmt = stmt.order_by(
            desc(func.count(JobSourceProvenance.job_id)),
            desc(Source.is_active),
            desc(Source.last_run_at).nullslast(),
            asc(Source.domain)
        )

    stmt = stmt.offset(offset).limit(limit)

    result = await db.execute(stmt)
    rows = result.all()

    items = []
    for s, cnt in rows:
        resp_item = SourceResponse(
            id=s.id,
            domain=s.domain,
            start_url=s.start_url,
            is_active=s.is_active,
            last_run_at=s.last_run_at,
            ats_type=s.ats_type,
            job_count=cnt or 0,
            consecutive_failures=s.consecutive_failures or 0,
            last_error=s.last_error,
            circuit_status=s.circuit_status.value if s.circuit_status else None,
            last_status_code=s.last_status_code,
            last_success_at=s.last_success_at,
            last_failure_at=s.last_failure_at,
        )
        items.append(resp_item)

    return PaginatedSourcesResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        pages=pages
    )

@router.post("", response_model=SourceResponse)
async def create_source(source: SourceCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Source).filter_by(domain=source.domain))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Source with this domain already exists")
        
    new_source = Source(
        id=str(uuid.uuid4()),
        domain=source.domain,
        start_url=source.start_url,
        ats_type=source.ats_type,
        is_active=True
    )
    db.add(new_source)
    await db.commit()
    await db.refresh(new_source)
    invalidate_source_stats_cache()
    return SourceResponse(
        id=new_source.id,
        domain=new_source.domain,
        start_url=new_source.start_url,
        is_active=new_source.is_active,
        last_run_at=new_source.last_run_at,
        ats_type=new_source.ats_type,
        job_count=0
    )

@router.patch("/{source_id}", response_model=SourceResponse)
async def update_source(source_id: str, updates: SourceUpdate, db: AsyncSession = Depends(get_db)):
    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
        
    if updates.domain is not None and updates.domain != source.domain:
        existing = await db.execute(select(Source).filter_by(domain=updates.domain))
        if existing.scalars().first():
            raise HTTPException(status_code=400, detail="Source with this domain already exists")
        source.domain = updates.domain
        
    if updates.start_url is not None:
        source.start_url = updates.start_url
    if updates.ats_type is not None:
        source.ats_type = updates.ats_type
    if updates.is_active is not None:
        source.is_active = updates.is_active
        
    await db.commit()
    await db.refresh(source)
    invalidate_source_stats_cache()
    
    cnt = await db.scalar(select(func.count(JobSourceProvenance.job_id)).where(JobSourceProvenance.source_id == source_id)) or 0
    return SourceResponse(
        id=source.id,
        domain=source.domain,
        start_url=source.start_url,
        is_active=source.is_active,
        last_run_at=source.last_run_at,
        ats_type=source.ats_type,
        job_count=cnt,
        consecutive_failures=source.consecutive_failures or 0,
        last_error=source.last_error,
        circuit_status=source.circuit_status.value if source.circuit_status else None
    )

@router.post("/{source_id}/toggle", response_model=SourceResponse)
async def toggle_source(source_id: str, db: AsyncSession = Depends(get_db)):
    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    source.is_active = not source.is_active
    await db.commit()
    await db.refresh(source)
    invalidate_source_stats_cache()
    cnt = await db.scalar(select(func.count(JobSourceProvenance.job_id)).where(JobSourceProvenance.source_id == source_id)) or 0
    return SourceResponse(
        id=source.id,
        domain=source.domain,
        start_url=source.start_url,
        is_active=source.is_active,
        last_run_at=source.last_run_at,
        ats_type=source.ats_type,
        job_count=cnt,
        consecutive_failures=source.consecutive_failures or 0,
        last_error=source.last_error,
        circuit_status=source.circuit_status.value if source.circuit_status else None
    )

@router.post("/{source_id}/scan")
async def scan_source(source_id: str, db: AsyncSession = Depends(get_db)):
    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    source.last_run_at = datetime.utcnow()
    await db.commit()

    # Trigger real background discovery scan
    asyncio.create_task(_execute_source_discovery(source_id))

    return {
        "status": "QUEUED",
        "message": f"Discovery scan triggered for {source.domain}",
        "source_id": source.id,
        "domain": source.domain
    }

@router.post("/fix-failing")
async def fix_failing_sources(limit: int = Query(25, ge=1, le=100), db: AsyncSession = Depends(get_db)):
    """Triggers background re-scan for failing sources to auto-diagnose and ingest jobs."""
    failing_sources = (await db.execute(
        select(Source.id)
        .where(or_(Source.consecutive_failures > 0, Source.last_error.isnot(None)))
        .order_by(desc(Source.consecutive_failures))
        .limit(limit)
    )).scalars().all()

    for sid in failing_sources:
        asyncio.create_task(_execute_source_discovery(sid))

    return {
        "status": "QUEUED",
        "message": f"Queued diagnostic re-scans for {len(failing_sources)} failing sources",
        "count": len(failing_sources)
    }

@router.post("/scan-pending")
async def scan_pending_sources(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    ats_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Triggers bulk real discovery scans on pending sources (sources with 0 jobs and no recorded errors).
    Prioritizes known direct ATS platforms (Greenhouse, Workable, Lever, Ashby, Keka, BambooHR, Zoho Recruit, etc.).
    Enqueues real discovery tasks to the ARQ worker queue (with local background task fallback).
    """
    from sqlalchemy import case

    redis_pool = getattr(request.app.state, "redis", None)

    pend_cond = or_(Source.consecutive_failures == 0, Source.consecutive_failures.is_(None))
    stmt = (
        select(Source)
        .where(
            Source.is_active.is_(True),
            Source.circuit_status != CircuitStatus.OPEN,
            pend_cond,
            Source.last_error.is_(None),
            Source.last_success_at.is_(None)
        )
    )

    if ats_type and ats_type.lower() != "all":
        if ats_type.lower() in ["custom", "direct"]:
            stmt = stmt.where(or_(Source.ats_type.is_(None), Source.ats_type == "", Source.ats_type == "custom"))
        else:
            stmt = stmt.where(Source.ats_type.ilike(f"%{ats_type.strip()}%"))

    # Prioritize known ATS platforms first
    known_ats_priority = case(
        (Source.ats_type.isnot(None) & (Source.ats_type != '') & (Source.ats_type != 'custom'), 1),
        else_=0
    )
    stmt = stmt.order_by(
        desc(known_ats_priority),
        Source.last_run_at.asc().nullsfirst(),
        Source.domain.asc()
    ).limit(limit)

    sources = (await db.execute(stmt)).scalars().all()

    queued = 0
    skipped = 0

    for s in sources:
        # Check if already queued or running
        existing = await db.scalar(
            select(func.count(Task.id)).where(
                Task.target_id == s.id,
                Task.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING])
            )
        )
        if existing and existing > 0:
            skipped += 1
            continue

        target_url = s.start_url or f"https://{s.domain}"
        tid = str(uuid.uuid4())
        task = Task(
            id=tid,
            target_id=s.id,
            worker_type="discovery_task",
            status=TaskStatus.QUEUED,
            created_at=datetime.now(timezone.utc)
        )
        db.add(task)
        db.add(TaskEvent(task_id=tid, event_type=TaskEventType.QUEUED, payload={"target_id": target_url, "source_id": s.id, "domain": s.domain, "trigger": "bulk_pending_scan"}))
        s.last_run_at = datetime.utcnow()
        await db.flush()

        if redis_pool:
            try:
                await redis_pool.enqueue_job("discovery_task", tid, target_url, _job_id=tid)
            except Exception as e:
                logger.warning(f"Redis enqueue failed, running as async task: {e}")
                asyncio.create_task(_execute_source_discovery(s.id))
        else:
            asyncio.create_task(_execute_source_discovery(s.id))

        queued += 1

    await db.commit()
    invalidate_source_stats_cache()

    return {
        "status": "QUEUED",
        "queued": queued,
        "skipped": skipped,
        "message": f"Successfully queued {queued} pending sources for real discovery scanning ({skipped} already running).",
    }

@router.delete("/{source_id}")
async def delete_source(source_id: str, db: AsyncSession = Depends(get_db)):
    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    await db.delete(source)
    await db.commit()
    invalidate_source_stats_cache()
    return {"message": "Source deleted successfully"}

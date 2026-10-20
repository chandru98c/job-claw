import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, or_

from app.database.database import get_db
from app.database.models import Job, Source, Task, TaskEvent, TaskStatus, TaskEventType

router = APIRouter(prefix="/engines", tags=["engines"])


@router.get("/metrics")
async def get_engine_metrics(
    page: int = 1,
    limit: int = 24,
    search: str | None = None,
    ats_type: str | None = None,
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db)
):
    jobs_count = int((await db.scalar(select(func.count(Job.id)))) or 0)
    sources_count = int((await db.scalar(select(func.count(Source.id)))) or 0)
    tasks_count = int((await db.scalar(select(func.count(Task.id)))) or 0)

    active_sources = int((await db.scalar(select(func.count(Source.id)).where(Source.is_active.is_(True)))) or 0)
    inactive_sources = max(sources_count - active_sources, 0)

    # ATS counts distribution
    ats_rows = (await db.execute(select(Source.ats_type, func.count(Source.id)).group_by(Source.ats_type))).all()
    ats_counts: dict[str, int] = {}
    for row in ats_rows:
        key = (row[0] or "custom").lower()
        ats_counts[key] = ats_counts.get(key, 0) + row[1]

    discovery_running = int(
        (
            await db.scalar(
                select(func.count(Task.id)).where(
                    Task.worker_type == "discovery_task",
                    Task.status == TaskStatus.RUNNING,
                )
            )
        )
        or 0
    )
    discovery_queued = int(
        (
            await db.scalar(
                select(func.count(Task.id)).where(
                    Task.worker_type == "discovery_task",
                    Task.status == TaskStatus.QUEUED,
                )
            )
        )
        or 0
    )

    # Pull latest discovery tasks for runtime visibility (capped at 100 recent for performance)
    task_rows = (
        await db.execute(
            select(Task)
            .where(Task.worker_type == "discovery_task")
            .order_by(Task.created_at.desc())
            .limit(100)
        )
    ).scalars().all()

    latest_task_by_target: dict[str, Task] = {}
    for task in task_rows:
        target_id = task.target_id
        if isinstance(target_id, str) and target_id not in latest_task_by_target:
            latest_task_by_target[target_id] = task

    # Build filtered query for sources
    stmt = select(Source)
    count_stmt = select(func.count(Source.id))

    if search:
        s_pat = f"%{search.strip()}%"
        cond = or_(Source.domain.ilike(s_pat), Source.start_url.ilike(s_pat))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    if ats_type and ats_type.lower() != "all":
        if ats_type.lower() in ["custom", "direct"]:
            cond = or_(Source.ats_type.is_(None), Source.ats_type == "", Source.ats_type == "custom")
        else:
            cond = Source.ats_type.ilike(f"%{ats_type.strip()}%")
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    if is_active is not None:
        stmt = stmt.where(Source.is_active.is_(is_active))
        count_stmt = count_stmt.where(Source.is_active.is_(is_active))

    filtered_total = int((await db.scalar(count_stmt)) or 0)
    pages = max((filtered_total + limit - 1) // limit, 1)

    offset = (page - 1) * limit
    source_rows = (
        await db.execute(
            stmt
            .order_by(Source.last_run_at.desc().nullslast(), Source.domain.asc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    engines: list[dict[str, Any]] = []
    for source in source_rows:
        raw_start_url = getattr(source, "start_url", None)
        raw_domain = getattr(source, "domain", None)
        start_url = raw_start_url if isinstance(raw_start_url, str) and raw_start_url.strip() else None
        domain = raw_domain if isinstance(raw_domain, str) and raw_domain.strip() else None

        lookup_candidates: list[str] = []
        if start_url is not None:
            lookup_candidates.append(start_url)
        if domain is not None:
            lookup_candidates.append(domain)
            lookup_candidates.append(f"https://{domain}")
            lookup_candidates.append(f"http://{domain}")

        last_task = None
        for key in lookup_candidates:
            if key in latest_task_by_target:
                last_task = latest_task_by_target[key]
                break

        runtime_status = "idle"
        runtime_error = None
        runtime_updated_at = None
        runtime_task_id = None

        if last_task:
            runtime_status = last_task.status.value
            runtime_error = last_task.error
            runtime_updated_at = last_task.finished_at or last_task.started_at or last_task.created_at
            runtime_task_id = last_task.id
        elif source.consecutive_failures and source.consecutive_failures > 0:
            runtime_status = "error"
            runtime_error = source.last_error
        elif source.last_run_at:
            runtime_status = "completed"

        engines.append(
            {
                "id": source.id,
                "domain": domain or "",
                "start_url": start_url,
                "ats_type": source.ats_type if isinstance(source.ats_type, str) else None,
                "is_active": bool(source.is_active),
                "last_run_at": source.last_run_at,
                "runtime": {
                    "status": runtime_status,
                    "error": runtime_error,
                    "updated_at": runtime_updated_at,
                    "task_id": runtime_task_id,
                },
            }
        )

    last_discovery_task = (
        await db.execute(
            select(Task)
            .where(Task.worker_type == "discovery_task")
            .order_by(Task.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    return {
        "metrics": {
            "total_jobs": jobs_count,
            "total_sources": sources_count,
            "active_sources": active_sources,
            "inactive_sources": inactive_sources,
            "total_tasks": tasks_count,
            "running_discovery_tasks": discovery_running,
            "queued_discovery_tasks": discovery_queued,
        },
        "discovery": {
            "state": "running" if (discovery_running + discovery_queued) > 0 else "idle",
            "last_task_status": last_discovery_task.status.value if last_discovery_task else None,
            "last_task_error": last_discovery_task.error if last_discovery_task else None,
        },
        "ats_counts": ats_counts,
        "total": filtered_total,
        "page": page,
        "limit": limit,
        "pages": pages,
        "engines": engines,
    }


@router.post("/discovery/run")
async def run_registry_discovery(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Queue discovery tasks for active registry sources using existing ARQ/task pipeline.
    """
    redis_pool = getattr(request.app.state, "redis", None)
    if not redis_pool:
        raise HTTPException(status_code=503, detail="Redis pool not configured")

    try:
        await redis_pool.ping()
    except Exception:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    active_sources = (
        await db.execute(select(Source).where(Source.is_active.is_(True)).order_by(Source.domain.asc()))
    ).scalars().all()

    if not active_sources:
        return {
            "queued": 0,
            "skipped": 0,
            "task_ids": [],
            "message": "No active registry sources found",
        }

    queued_task_ids: list[str] = []
    skipped = 0

    for source in active_sources:
        raw_start_url = getattr(source, "start_url", None)
        raw_domain = getattr(source, "domain", None)
        start_url = raw_start_url if isinstance(raw_start_url, str) and raw_start_url.strip() else None
        domain = raw_domain if isinstance(raw_domain, str) and raw_domain.strip() else None

        input_url = start_url if start_url is not None else (f"https://{domain}" if domain is not None else None)
        if input_url is None:
            skipped += 1
            continue

        lock_id = hash(f"discovery_task_{input_url}") & 0x7FFFFFFFFFFFFFFF
        await db.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": lock_id})

        existing_task = (
            await db.execute(
                select(Task).where(
                    Task.target_id == source.id,
                    Task.worker_type == "discovery_task",
                    Task.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING]),
                )
            )
        ).scalar_one_or_none()

        if existing_task:
            skipped += 1
            continue

        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            target_id=source.id,
            worker_type="discovery_task",
            status=TaskStatus.QUEUED,
            created_at=datetime.now(timezone.utc),
        )
        db.add(task)
        db.add(
            TaskEvent(
                task_id=task_id,
                event_type=TaskEventType.QUEUED,
                payload={"target_id": input_url, "source_id": source.id, "domain": domain},
            )
        )
        await db.flush()

        enqueued = await redis_pool.enqueue_job("discovery_task", task_id, input_url, _job_id=task_id)
        if not enqueued:
            raise HTTPException(status_code=500, detail=f"Failed to enqueue discovery task for {domain or source.id}")

        queued_task_ids.append(task_id)

    await db.commit()

    return {
        "queued": len(queued_task_ids),
        "skipped": skipped,
        "task_ids": queued_task_ids,
        "message": "Discovery queued for active registry sources",
    }

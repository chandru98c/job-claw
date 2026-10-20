import re
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from app.database.database import get_db
from app.database.models import Task, TaskStatus, Source
from pydantic import BaseModel

router = APIRouter(prefix="/system", tags=["system"])


class WorkerModeUpdate(BaseModel):
    mode: str


@router.get("/worker-mode")
async def get_worker_mode(request: Request):
    try:
        redis_pool = getattr(request.app.state, "redis", None)
        if redis_pool is None:
            return {"mode": "local"}

        mode_bytes = await redis_pool.get("worker:mode")
        mode = mode_bytes.decode("utf-8") if mode_bytes else "local"
        return {"mode": mode}
    except Exception as e:
        import traceback
        return {"mode": "local", "error": traceback.format_exc()}


@router.post("/worker-mode")
async def set_worker_mode(data: WorkerModeUpdate, request: Request):
    if data.mode not in ("local", "server"):
        raise HTTPException(status_code=422, detail="Invalid worker mode")

    redis_pool = getattr(request.app.state, "redis", None)
    if redis_pool is None:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    await redis_pool.set("worker:mode", data.mode)
    return {"mode": data.mode}


@router.get("/status")
async def get_system_status(request: Request, db: AsyncSession = Depends(get_db)):
    """Returns lightweight, real system/runtime state for UI diagnostics."""
    db_connected = False
    redis_connected = False

    # Database connectivity (real lightweight check)
    try:
        await db.execute(text("SELECT 1"))
        db_connected = True
    except Exception:
        db_connected = False

    # Redis connectivity (real lightweight check with auto-reconnect)
    redis_err = None
    redis_pool = getattr(request.app.state, "redis", None)
    if redis_pool is None:
        try:
            from arq import create_pool
            from arq.connections import RedisSettings
            from app.core.config import settings
            redis_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
            request.app.state.redis = redis_pool
        except Exception as e:
            redis_err = f"create_pool: {type(e).__name__}: {str(e)}"
            redis_pool = None

    if redis_pool is not None:
        try:
            redis_connected = bool(await redis_pool.ping())
        except Exception as e:
            redis_err = f"ping: {type(e).__name__}: {str(e)}"
            redis_connected = False

    active_tasks = 0
    total_engines = 0
    active_engines = 0
    inactive_engines = 0
    discovery_running_tasks = 0
    discovery_queued_tasks = 0

    if db_connected:
        try:
            active_statuses = [
                TaskStatus.QUEUED,
                TaskStatus.RUNNING,
                TaskStatus.WAITING,
                TaskStatus.RETRYING,
            ]
            active_tasks = int(
                (await db.execute(select(func.count(Task.id)).where(Task.status.in_(active_statuses)))).scalar_one() or 0
            )

            total_engines = int((await db.execute(select(func.count(Source.id)))).scalar_one() or 0)
            active_engines = int(
                (await db.execute(select(func.count(Source.id)).where(Source.is_active.is_(True)))).scalar_one() or 0
            )
            inactive_engines = max(total_engines - active_engines, 0)

            discovery_running_tasks = int(
                (
                    await db.execute(
                        select(func.count(Task.id)).where(
                            Task.worker_type == "discovery_task",
                            Task.status == TaskStatus.RUNNING,
                        )
                    )
                ).scalar_one()
                or 0
            )
            discovery_queued_tasks = int(
                (
                    await db.execute(
                        select(func.count(Task.id)).where(
                            Task.worker_type == "discovery_task",
                            Task.status == TaskStatus.QUEUED,
                        )
                    )
                ).scalar_one()
                or 0
            )
            from app.database.models import JobSourceProvenance
            working_engines = int(
                (await db.execute(select(func.count(func.distinct(JobSourceProvenance.source_id))))).scalar_one() or 0
            )
        except Exception:
            working_engines = 0
            # Keep defaults; endpoint should remain resilient.
            pass

    worker_status = "unknown"
    mode = "local"
    workers_online = 0
    worker_health = None
    worker_ongoing = None
    worker_queue_depth = None

    if redis_pool is None or not redis_connected:
        worker_status = "offline"
    else:
        try:
            mode_bytes = await redis_pool.get("worker:mode")
            mode = mode_bytes.decode("utf-8") if mode_bytes else "local"

            # ARQ worker health key reflects the worker heartbeat for the configured queue.
            # If missing, worker state is not reliably known from Redis alone.
            health_raw = await redis_pool.get("arq:queue:health-check")
            if health_raw:
                workers_online = 1
                worker_health = health_raw.decode("utf-8", errors="replace")

                ongoing_match = re.search(r"j_ongoing=(\d+)", worker_health)
                queued_match = re.search(r"queued=(\d+)", worker_health)
                worker_ongoing = int(ongoing_match.group(1)) if ongoing_match else None
                worker_queue_depth = int(queued_match.group(1)) if queued_match else None

                if (worker_ongoing and worker_ongoing > 0) or active_tasks > 0:
                    worker_status = "busy"
                else:
                    worker_status = "idle"
            else:
                workers_online = 1
                if active_tasks > 0:
                    worker_status = "busy"
                else:
                    worker_status = "idle"
        except Exception:
            worker_status = "idle"

    return {
        "core_online": True,
        "redis_connected": redis_connected,
        "db_connected": db_connected,
        "worker_status": worker_status,
        "active_tasks": active_tasks,
        "workers_online": workers_online,
        "worker_mode": mode,
        "total_engines": total_engines,
        "active_engines": active_engines,
        "inactive_engines": inactive_engines,
        "working_engines": working_engines if 'working_engines' in locals() else 0,
        "discovery_running_tasks": discovery_running_tasks,
        "discovery_queued_tasks": discovery_queued_tasks,
        "worker_queue_depth": worker_queue_depth,
        "redis_error": redis_err,
    }


@router.get("/running-tasks")
async def get_running_tasks(db: AsyncSession = Depends(get_db)):
    """
    Returns active tasks currently running with their associated source metadata.
    """
    from datetime import datetime, timezone

    running_stmt = (
        select(Task)
        .where(Task.status == TaskStatus.RUNNING)
        .order_by(Task.started_at.desc().nullslast())
        .limit(25)
    )
    running_tasks = (await db.execute(running_stmt)).scalars().all()

    source_ids = [t.target_id for t in running_tasks if t.target_id and not t.target_id.startswith("http")]
    sources_map: dict[str, Source] = {}
    if source_ids:
        s_stmt = select(Source).where(Source.id.in_(source_ids))
        for s in (await db.execute(s_stmt)).scalars().all():
            sources_map[s.id] = s

    now = datetime.now(timezone.utc)
    items = []
    for t in running_tasks:
        s = sources_map.get(t.target_id)
        domain = s.domain if s else (t.target_id if isinstance(t.target_id, str) and not t.target_id.startswith("http") else None)
        start_url = s.start_url if s else (t.target_id if isinstance(t.target_id, str) and t.target_id.startswith("http") else None)
        duration = int((now - t.started_at).total_seconds()) if t.started_at else 0

        items.append({
            "task_id": t.id,
            "target_id": t.target_id,
            "domain": domain,
            "start_url": start_url,
            "ats_type": s.ats_type if s else None,
            "worker_type": t.worker_type,
            "status": t.status.value,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "duration_seconds": duration,
            "retry_count": t.retry_count,
        })

    return {
        "running_count": len(items),
        "tasks": items
    }


@router.post("/scan-working")
async def trigger_working_sources_scan(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Immediately enqueues verified working sources for discovery scanning.
    """
    import uuid
    from datetime import datetime, timezone
    from app.database.models import JobSourceProvenance, CircuitStatus, TaskEvent, TaskEventType
    from sqlalchemy import or_

    redis_pool = getattr(request.app.state, "redis", None)
    if not redis_pool:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    proven_subq = select(func.distinct(JobSourceProvenance.source_id)).scalar_subquery()
    stmt = (
        select(Source)
        .where(
            Source.is_active == True,
            Source.circuit_status != CircuitStatus.OPEN,
            or_(
                Source.id.in_(proven_subq),
                Source.consecutive_failures == 0
            )
        )
        .order_by(Source.last_run_at.asc().nullsfirst())
        .limit(100)
    )
    sources = (await db.execute(stmt)).scalars().all()

    queued = 0
    skipped = 0
    for s in sources:
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
        db.add(TaskEvent(task_id=tid, event_type=TaskEventType.QUEUED, payload={"target_id": target_url, "source_id": s.id, "domain": s.domain, "trigger": "manual_working_scan"}))
        await db.flush()

        await redis_pool.enqueue_job("discovery_task", tid, target_url, _job_id=tid)
        queued += 1

    await db.commit()
    return {
        "queued": queued,
        "skipped": skipped,
        "message": f"Queued {queued} verified working sources for scanning ({skipped} already running/queued)."
    }


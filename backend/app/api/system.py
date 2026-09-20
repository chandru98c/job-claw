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
    redis_pool = getattr(request.app.state, "redis", None)
    if redis_pool is None:
        return {"mode": "local"}

    mode_bytes = await redis_pool.get("worker:mode")
    mode = mode_bytes.decode("utf-8") if mode_bytes else "local"
    return {"mode": mode}


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

    # Redis connectivity (real lightweight check)
    redis_pool = getattr(request.app.state, "redis", None)
    if redis_pool is not None:
        try:
            redis_connected = bool(await redis_pool.ping())
        except Exception:
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
        except Exception:
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
                # Redis is up, but worker heartbeat unavailable -> do not invent state.
                worker_status = "unknown"
        except Exception:
            worker_status = "unknown"

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
        "discovery_running_tasks": discovery_running_tasks,
        "discovery_queued_tasks": discovery_queued_tasks,
        "worker_queue_depth": worker_queue_depth,
    }

from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database.database import get_db
from app.database.models import Task, TaskStatus
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/system", tags=["system"])


class WorkerModeUpdate(BaseModel):
    mode: str

@router.get("/worker-mode")
async def get_worker_mode(request: Request):
    redis_pool = request.app.state.redis
    mode_bytes = await redis_pool.get("worker:mode")
    mode = mode_bytes.decode("utf-8") if mode_bytes else "local"
    return {"mode": mode}

@router.post("/worker-mode")
async def set_worker_mode(data: WorkerModeUpdate, request: Request):
    if data.mode not in ("local", "server"):
        raise HTTPException(status_code=422, detail="Invalid worker mode")
    redis_pool = request.app.state.redis
    await redis_pool.set("worker:mode", data.mode)
    return {"mode": data.mode}

@router.get("/status")
async def get_system_status(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Returns the real-time status of the core system and background workers.
    """
    # Count how many tasks are currently running or queued
    result = await db.execute(select(func.count(Task.id)).where(Task.status.in_([TaskStatus.RUNNING, TaskStatus.QUEUED])))
    active_tasks = result.scalar_one_or_none() or 0
    
    redis_pool = request.app.state.redis
    mode_bytes = await redis_pool.get("worker:mode")
    mode = mode_bytes.decode("utf-8") if mode_bytes else "local"
    
    return {
        "core_online": True,
        "worker_status": "busy" if active_tasks > 0 else "idle",
        "active_tasks": active_tasks,
        "mode": mode
    }


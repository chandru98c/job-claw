import os
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database.database import get_db
from app.database.models import Job, Source, Task

router = APIRouter(prefix="/engines", tags=["engines"])

@router.get("/metrics")
async def get_engine_metrics(db: AsyncSession = Depends(get_db)):
    # Get total jobs
    jobs_count = await db.scalar(select(func.count(Job.id)))
    # Get total sources
    sources_count = await db.scalar(select(func.count(Source.id)))
    # Get total tasks run
    tasks_count = await db.scalar(select(func.count(Task.id)))
    
    # Dynamically find adapters
    adapters_dir = os.path.join(os.path.dirname(__file__), "..", "discovery", "adapters")
    registered_adapters = []
    
    if os.path.exists(adapters_dir):
        for file in os.listdir(adapters_dir):
            if file.endswith(".py") and file != "__init__.py" and file != "base.py":
                name = file.replace(".py", "").capitalize()
                registered_adapters.append({
                    "name": name,
                    "status": "Operational",
                    "type": "HTTP + Playwright" if name in ["Greenhouse", "Smartrecruiters", "Lever"] else "HTTP Only",
                })
                
    return {
        "metrics": {
            "total_jobs": jobs_count or 0,
            "total_sources": sources_count or 0,
            "total_tasks": tasks_count or 0,
        },
        "adapters": registered_adapters
    }

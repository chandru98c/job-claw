from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.database.database import get_db
from app.database.models import Source

router = APIRouter(prefix="/sources", tags=["sources"])

class SourceResponse(BaseModel):
    id: str
    domain: str
    start_url: Optional[str]
    is_active: bool
    last_run_at: Optional[datetime]
    ats_type: Optional[str]

    class Config:
        from_attributes = True

@router.get("", response_model=List[SourceResponse])
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Source).order_by(Source.domain))
    sources = result.scalars().all()
    return sources

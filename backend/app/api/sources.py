from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.database.database import get_db
from app.database.models import Source

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

    class Config:
        from_attributes = True

@router.get("", response_model=List[SourceResponse])
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Source).order_by(Source.domain))
    sources = result.scalars().all()
    return sources

@router.post("", response_model=SourceResponse)
async def create_source(source: SourceCreate, db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException
    
    # Check for duplicates
    existing = await db.execute(select(Source).filter_by(domain=source.domain))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Source with this domain already exists")
        
    import uuid
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
    return new_source

@router.patch("/{source_id}", response_model=SourceResponse)
async def update_source(source_id: str, updates: SourceUpdate, db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException
    
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
    return source

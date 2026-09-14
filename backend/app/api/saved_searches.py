from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from typing import List
from datetime import datetime

from app.database.database import get_db
from app.database.models import SavedSearch, Profile
from app.schemas.saved_search import SavedSearchCreate, SavedSearchUpdate, SavedSearchResponse
from app.core.security import get_current_profile_id # Assume this exists from Phase 11/earlier

router = APIRouter(prefix="/saved-searches", tags=["Saved Searches"])

@router.get("", response_model=List[SavedSearchResponse])
async def get_saved_searches(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    profile_id = get_current_profile_id(request)
    result = await db.execute(select(SavedSearch).where(SavedSearch.profile_id == profile_id))
    return result.scalars().all()

@router.post("", response_model=SavedSearchResponse, status_code=201)
async def create_saved_search(
    data: SavedSearchCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    profile_id = get_current_profile_id(request)
    
    new_search = SavedSearch(
        profile_id=profile_id,
        name=data.name,
        query=data.query,
        location=data.location,
        remote=data.remote,
        enabled=data.enabled
    )
    db.add(new_search)
    await db.commit()
    await db.refresh(new_search)
    return new_search

@router.get("/{search_id}", response_model=SavedSearchResponse)
async def get_saved_search(
    search_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    profile_id = get_current_profile_id(request)
    result = await db.execute(select(SavedSearch).where(SavedSearch.id == search_id, SavedSearch.profile_id == profile_id))
    search = result.scalar_one_or_none()
    if not search:
        raise HTTPException(status_code=404, detail="Saved search not found")
    return search

@router.patch("/{search_id}", response_model=SavedSearchResponse)
async def update_saved_search(
    search_id: str,
    data: SavedSearchUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    profile_id = get_current_profile_id(request)
    result = await db.execute(select(SavedSearch).where(SavedSearch.id == search_id, SavedSearch.profile_id == profile_id))
    search = result.scalar_one_or_none()
    if not search:
        raise HTTPException(status_code=404, detail="Saved search not found")
        
    for k, v in data.dict(exclude_unset=True).items():
        setattr(search, k, v)
        
    await db.commit()
    await db.refresh(search)
    return search

@router.delete("/{search_id}", status_code=204)
async def delete_saved_search(
    search_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    profile_id = get_current_profile_id(request)
    result = await db.execute(select(SavedSearch).where(SavedSearch.id == search_id, SavedSearch.profile_id == profile_id))
    search = result.scalar_one_or_none()
    if not search:
        raise HTTPException(status_code=404, detail="Saved search not found")
        
    await db.delete(search)
    await db.commit()
    return None

@router.post("/{search_id}/run", status_code=202)
async def run_saved_search(
    search_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    profile_id = get_current_profile_id(request)
    result = await db.execute(select(SavedSearch).where(SavedSearch.id == search_id, SavedSearch.profile_id == profile_id))
    search = result.scalar_one_or_none()
    if not search:
        raise HTTPException(status_code=404, detail="Saved search not found")
    
    # Enqueue task
    if not hasattr(request.app.state, "redis"):
        raise HTTPException(status_code=500, detail="Redis connection unavailable")
        
    await request.app.state.redis.enqueue_job(
        "execute_saved_search_task",
        search_id
    )
    
    return {"message": "Saved search run queued"}

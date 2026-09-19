from fastapi import APIRouter, Depends, Request, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
import os
import shutil
import uuid

from app.database.database import get_db
from app.database.models import Profile
from app.core.security import get_valid_profile

router = APIRouter(prefix="/profiles", tags=["profiles"])

class ProfileCreate(BaseModel):
    name: str

@router.get("")
@router.get("/")
async def list_profiles(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Profile))
    profiles = res.scalars().all()
    return [{"id": p.id, "name": p.name} for p in profiles]

@router.post("")
@router.post("/")
async def create_profile(data: ProfileCreate, db: AsyncSession = Depends(get_db)):
    new_id = str(uuid.uuid4())
    profile = Profile(id=new_id, name=data.name)
    db.add(profile)
    await db.commit()
    return {"id": profile.id, "name": profile.name}

class ProfileUpdate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    tagline: Optional[str] = None
    about: Optional[str] = None
    skills: Optional[List[str]] = None
    interested_fields: Optional[List[str]] = None
    preferred_locations: Optional[List[str]] = None
    preferred_job_types: Optional[List[str]] = None

@router.get("/me")
async def get_my_profile(profile: Profile = Depends(get_valid_profile)):
    return {
        "id": profile.id,
        "name": profile.name,
        "email": profile.email,
        "phone": profile.phone,
        "location": profile.location,
        "tagline": profile.tagline,
        "about": profile.about,
        "skills": profile.skills or [],
        "interested_fields": profile.interested_fields or [],
        "preferred_locations": profile.preferred_locations or [],
        "preferred_job_types": profile.preferred_job_types or [],
        "resume_path": profile.resume_path
    }

@router.put("/me")
async def update_my_profile(
    data: ProfileUpdate,
    profile: Profile = Depends(get_valid_profile),
    db: AsyncSession = Depends(get_db)
):
    profile.name = data.name
    if data.email is not None: profile.email = data.email
    if data.phone is not None: profile.phone = data.phone
    if data.location is not None: profile.location = data.location
    if data.tagline is not None: profile.tagline = data.tagline
    if data.about is not None: profile.about = data.about
    if data.skills is not None: profile.skills = data.skills
    if data.interested_fields is not None: profile.interested_fields = data.interested_fields
    if data.preferred_locations is not None: profile.preferred_locations = data.preferred_locations
    if data.preferred_job_types is not None: profile.preferred_job_types = data.preferred_job_types
    
    await db.commit()
    await db.refresh(profile)
    
    return {
        "id": profile.id,
        "name": profile.name,
        "email": profile.email,
        "phone": profile.phone,
        "location": profile.location,
        "tagline": profile.tagline,
        "about": profile.about,
        "skills": profile.skills or [],
        "interested_fields": profile.interested_fields or [],
        "preferred_locations": profile.preferred_locations or [],
        "preferred_job_types": profile.preferred_job_types or [],
        "resume_path": profile.resume_path
    }

@router.post("/me/resume")
async def upload_resume(
    file: UploadFile = File(...),
    profile: Profile = Depends(get_valid_profile),
    db: AsyncSession = Depends(get_db)
):
    # Safe storage directory
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data/resumes"))
    os.makedirs(data_dir, exist_ok=True)
    
    # Very strict safe filename constraint to avoid directory traversal
    filename = "".join(c for c in file.filename if c.isalnum() or c in ".-_")
    if not filename:
        filename = "resume.pdf"
        
    filepath = os.path.join(data_dir, f"{profile_id}_{filename}")
    
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    profile.resume_path = filepath
    await db.commit()
    
    return {"message": "Resume uploaded successfully", "resume_path": filepath}

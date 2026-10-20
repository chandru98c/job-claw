from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.database.models import RecommendationState

class JobRecommendationBase(BaseModel):
    state: RecommendationState = RecommendationState.NEW

class JobRecommendationUpdate(BaseModel):
    state: RecommendationState

class JobRecommendationResponse(JobRecommendationBase):
    id: str
    profile_id: str
    job_id: str
    score: int
    reasons: Optional[List[str]] = None
    
    application_id: Optional[str] = None
    task_id: Optional[str] = None
    
    # Enriched Job Information
    title: Optional[str] = None
    company_name: Optional[str] = None
    location: Optional[str] = None
    job_type: Optional[str] = None
    apply_url: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    remote_status: Optional[str] = None
    matched_skills: Optional[List[str]] = None
    experience_level: Optional[str] = None
    education_level: Optional[str] = None
    role_category: Optional[str] = None
    corridor: Optional[str] = None
    city: Optional[str] = None
    posted_at: Optional[datetime] = None
    
    first_seen_at: datetime
    surfaced_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None
    
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class RecommendationAction(BaseModel):
    action: str # 'save', 'dismiss', 'prepare'

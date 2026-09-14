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
    
    first_seen_at: datetime
    surfaced_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None
    
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class RecommendationAction(BaseModel):
    action: str # 'save', 'dismiss', 'prepare'

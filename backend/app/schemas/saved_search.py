from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class SavedSearchCreate(BaseModel):
    name: str = Field(..., max_length=100)
    query: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=100)
    remote: Optional[bool] = None
    enabled: bool = True

class SavedSearchUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    query: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=100)
    remote: Optional[bool] = None
    enabled: Optional[bool] = None

class SavedSearchResponse(SavedSearchCreate):
    id: str
    profile_id: str
    last_run_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

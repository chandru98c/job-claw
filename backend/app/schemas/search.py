import re
from pydantic import BaseModel, Field, validator
from typing import List, Optional

class SearchQuery(BaseModel):
    q: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=100)
    remote: Optional[bool] = None
    page: int = Field(1, ge=1)
    limit: int = Field(20, ge=1, le=100)

    @validator("q", "location", pre=True)
    def normalize_text(cls, v):
        if v is None:
            return v
        # Normalize whitespace
        v = re.sub(r'\s+', ' ', str(v)).strip()
        if len(v) > 100:
            v = v[:100]
        return v if v else None

class JobMatchResult(BaseModel):
    id: str
    title: str
    company_name: str
    location: Optional[str]
    job_type: Optional[str]
    canonical_apply_url: str
    status: str
    matchScore: Optional[int] = None
    matchReasons: Optional[List[str]] = None
    timeAgo: str

class SearchResponse(BaseModel):
    items: List[JobMatchResult]
    total: int
    page: int
    limit: int

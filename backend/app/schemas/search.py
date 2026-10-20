import re
from pydantic import BaseModel, Field, validator
from typing import List, Optional

class SearchQuery(BaseModel):
    q: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=100)
    remote: Optional[bool] = None
    role: Optional[str] = Field(None, max_length=50)              # e.g. "software_engineer", "frontend", "backend", "fullstack", "data_ai", "devops_cloud", "qa_testing"
    degree: Optional[str] = Field(None, max_length=50)            # e.g. "MCA", "B.Tech", "M.Tech", "Any Graduate"
    salary_min: Optional[float] = Field(None, ge=0)               # e.g. 300000 (3 LPA) or 50000 (USD)
    salary_max: Optional[float] = Field(None, ge=0)               # e.g. 1000000 (10 LPA) or 150000 (USD)
    job_type: Optional[str] = Field(None, max_length=50)          # e.g. "Full-time", "Internship", "Contract"
    experience_level: Optional[str] = Field(None, max_length=50)  # e.g. "fresher", "junior", "mid", "senior"
    sort_by: Optional[str] = Field("recent", pattern="^(recent|score)$")
    page: int = Field(1, ge=1)
    limit: int = Field(20, ge=1, le=100)

    @validator("q", "location", "role", "degree", "job_type", "experience_level", pre=True)
    def normalize_text(cls, v):
        if v is None:
            return v
        v = re.sub(r'\s+', ' ', str(v)).strip()
        if len(v) > 100:
            v = v[:100]
        return v if v else None

class JobMatchResult(BaseModel):
    id: str
    title: str
    company_name: str
    location: Optional[str] = None
    job_type: Optional[str] = None
    canonical_apply_url: Optional[str] = None
    status: str
    matchScore: Optional[int] = None
    matchReasons: Optional[List[str]] = None
    timeAgo: str
    # Enriched fields
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None
    education_level: Optional[str] = None
    role_category: Optional[str] = None
    experience_level: Optional[str] = None
    corridor: Optional[str] = None
    city: Optional[str] = None
    created_at: Optional[str] = None
    discovered_at: Optional[str] = None

class SearchResponse(BaseModel):
    items: List[JobMatchResult]
    total: int
    page: int
    limit: int

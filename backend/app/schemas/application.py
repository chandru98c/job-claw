from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
import enum
from datetime import datetime

class FieldSource(str, enum.Enum):
    PROFILE = "PROFILE"
    USER_INPUT = "USER_INPUT"
    SYSTEM_DETECTED = "SYSTEM_DETECTED"
    UNMAPPED = "UNMAPPED"
    REQUIRES_USER_INPUT = "REQUIRES_USER_INPUT"

class ApplicationField(BaseModel):
    field_id: str
    label: str
    type: str
    required: bool
    options: Optional[List[str]] = None
    placeholder: Optional[str] = None
    value: Optional[Any] = None
    source: FieldSource = FieldSource.UNMAPPED

class ApplicationDraft(BaseModel):
    application_id: str
    job_id: str
    destination: str
    fields: List[ApplicationField]
    unanswered_required_fields: List[str]
    resume_reference: Optional[str] = None
    ready_for_submission: bool

class ApplicationCreate(BaseModel):
    job_id: str

class ApplicationUpdateField(BaseModel):
    field_id: str
    value: Any

class ApplicationApproval(BaseModel):
    # Endpoint will be POST /applications/{id}/approve
    # The frontend just confirms it. Backend revalidates everything.
    pass

class ApplicationResponse(BaseModel):
    id: str
    job_id: str
    profile_id: str
    status: str
    application_url: Optional[str]
    fields: Optional[List[ApplicationField]]
    unanswered_required_fields: Optional[List[str]]
    submission_evidence: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

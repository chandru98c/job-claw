from pydantic import BaseModel
from typing import Optional
from enum import Enum
from datetime import datetime, timezone

class VerificationOutcome(str, Enum):
    CONFIRMED_PRESENT = "CONFIRMED_PRESENT"
    CONFIRMED_MISSING = "CONFIRMED_MISSING"
    BLOCKED = "BLOCKED"
    TRANSIENT_FAILURE = "TRANSIENT_FAILURE"
    AMBIGUOUS = "AMBIGUOUS"

class VerificationReason(str, Enum):
    ACTIVE_CONFIRMED = "ACTIVE_CONFIRMED"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    HTTP_404 = "HTTP_404"
    HTTP_410 = "HTTP_410"
    REDIRECTED_EXTERNALLY = "REDIRECTED_EXTERNALLY"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    SERVER_ERROR = "SERVER_ERROR"
    AMBIGUOUS = "AMBIGUOUS"

class VerificationResult(BaseModel):
    """
    Deterministic evidence DTO from the verification engine.
    This does NOT dictate the JobStatus directly; the lifecycle engine consumes this.
    """
    outcome: VerificationOutcome
    reason: VerificationReason
    http_status: Optional[int] = None
    reachable: bool
    job_present: Optional[bool] = None
    verified_at: datetime = datetime.now(timezone.utc)

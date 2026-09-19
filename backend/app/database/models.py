import uuid
import enum
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, JSON, ForeignKey, Float, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

def generate_uuid():
    return str(uuid.uuid4())

class JobStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    VERIFYING = "VERIFYING"
    EXPIRED = "EXPIRED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"

class TaskStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    RETRYING = "RETRYING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class TaskEventType(str, enum.Enum):
    QUEUED = "QUEUED"
    STARTED = "STARTED"
    PROGRESS = "PROGRESS"
    RETRY = "RETRY"
    WARNING = "WARNING"
    ERROR = "ERROR"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class Source(Base):
    __tablename__ = "sources"

    id = Column(String, primary_key=True, default=generate_uuid)
    domain = Column(String, unique=True, index=True, nullable=False)
    start_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    ats_type = Column(String, nullable=True)
    discovered_endpoints = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    job_provenances = relationship("JobSourceProvenance", back_populates="source")


class Job(Base):
    """The Canonical Job"""
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=generate_uuid)
    
    # Core canonical fields
    title = Column(String, nullable=False, index=True)
    company_name = Column(String, nullable=False, index=True)
    location = Column(String, nullable=True)
    job_type = Column(String, nullable=True)
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    salary_currency = Column(String, nullable=True)
    
    canonical_apply_url = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    remote_status = Column(String, nullable=True)
    
    # Freshness state machine
    status = Column(Enum(JobStatus), default=JobStatus.UNKNOWN, index=True)
    last_source_seen_at = Column(DateTime(timezone=True), nullable=True)
    last_verified_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    provenances = relationship("JobSourceProvenance", back_populates="job", cascade="all, delete-orphan")
    versions = relationship("JobVersion", back_populates="job", cascade="all, delete-orphan")

class JobSourceProvenance(Base):
    """Maps a canonical job to the multiple sources (Employer ATS, LinkedIn, Indeed) it was found on"""
    __tablename__ = "job_source_provenances"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    source_id = Column(String, ForeignKey("sources.id"), nullable=True) # nullable because it might be an external aggregator
    
    source_type = Column(String, nullable=False) # e.g., 'direct_ats', 'linkedin', 'indeed'
    source_job_id = Column(String, nullable=True) # The ID used by the source
    source_url = Column(String, nullable=False)
    
    raw_payload = Column(JSON, nullable=True) # Bounded payload for debugging
    observed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    job = relationship("Job", back_populates="provenances")
    source = relationship("Source", back_populates="job_provenances")

class JobVersion(Base):
    """Preserves history of meaningful changes (salary, description, title)"""
    __tablename__ = "job_versions"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    
    changed_fields = Column(JSON, nullable=False) # e.g., ["salary_max", "description"]
    previous_state = Column(JSON, nullable=False) # Snapshot of what it was
    new_state = Column(JSON, nullable=False) # Snapshot of what it became
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    job = relationship("Job", back_populates="versions")

class Profile(Base):
    """Candidate Profiles for matching & auto-apply"""
    __tablename__ = "profiles"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    
    # Auto-Apply / Matching Fields
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    location = Column(String, nullable=True)
    tagline = Column(String, nullable=True)
    about = Column(Text, nullable=True)
    
    skills = Column(JSON, default=list)
    interested_fields = Column(JSON, default=list)
    preferred_locations = Column(JSON, default=list)
    preferred_job_types = Column(JSON, default=list)
    
    resume_path = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Task(Base):
    """Tracks every worker execution"""
    __tablename__ = "tasks"
    
    id = Column(String, primary_key=True) # Maps to ARQ/Redis task ID
    target_id = Column(String, nullable=True) # The source or profile this task relates to
    worker_type = Column(String, nullable=False) # e.g., 'DiscoveryWorker', 'AcquisitionWorker'
    
    status = Column(Enum(TaskStatus), default=TaskStatus.QUEUED, index=True)
    error = Column(Text, nullable=True)
    metrics = Column(JSON, nullable=True)
    retry_count = Column(Integer, default=0)
    
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    events = relationship("TaskEvent", back_populates="task", cascade="all, delete-orphan", order_by="TaskEvent.created_at")

class TaskEvent(Base):
    """Immutable log of significant events during task execution"""
    __tablename__ = "task_events"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False, index=True)
    
    event_type = Column(Enum(TaskEventType), nullable=False)
    payload = Column(JSON, nullable=True) # Context about the event (e.g. progress percentage, error traceback)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    task = relationship("Task", back_populates="events")
class ApplicationStatus(str, enum.Enum):
    PREPARING = "PREPARING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED = "APPROVED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    SUBMISSION_STATUS_UNKNOWN = "SUBMISSION_STATUS_UNKNOWN"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNSUPPORTED = "UNSUPPORTED"

class Application(Base):
    """Auto-Apply Application Record"""
    __tablename__ = "applications"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False, index=True)
    profile_id = Column(String, ForeignKey("profiles.id"), nullable=False, index=True)
    
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.PREPARING, index=True)
    application_url = Column(String, nullable=True) # Provenance URL
    
    fields = Column(JSON, nullable=True) # The structured draft
    unanswered_required_fields = Column(JSON, nullable=True)
    submission_evidence = Column(JSON, nullable=True) # Result evidence
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    __table_args__ = (
        # Ensure one application per job per profile
        UniqueConstraint('job_id', 'profile_id', name='uq_application_job_profile'),
    )
    
    job = relationship("Job")
    profile = relationship("Profile")

class SavedSearch(Base):
    """User-persisted search query and filters for scheduled discovery"""
    __tablename__ = "saved_searches"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    profile_id = Column(String, ForeignKey("profiles.id"), nullable=False, index=True)
    
    name = Column(String, nullable=False)
    query = Column(String, nullable=True) # Max 100 chars
    location = Column(String, nullable=True) # Max 100 chars
    remote = Column(Boolean, nullable=True)
    
    enabled = Column(Boolean, default=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    profile = relationship("Profile")

class RecommendationState(str, enum.Enum):
    NEW = "NEW"
    SEEN = "SEEN"
    SAVED = "SAVED"
    DISMISSED = "DISMISSED"
    APPLIED = "APPLIED"
    EXPIRED = "EXPIRED"

class JobRecommendation(Base):
    """Ranked job surfaceable to a profile"""
    __tablename__ = "job_recommendations"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    profile_id = Column(String, ForeignKey("profiles.id"), nullable=False, index=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False, index=True)
    
    score = Column(Integer, nullable=False)
    reasons = Column(JSON, nullable=True)
    state = Column(Enum(RecommendationState), default=RecommendationState.NEW, index=True)
    
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    surfaced_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('profile_id', 'job_id', name='uq_recommendation_profile_job'),
    )
    
    profile = relationship("Profile")
    job = relationship("Job")

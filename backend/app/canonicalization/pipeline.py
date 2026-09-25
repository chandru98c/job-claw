import json
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Tuple

from app.schemas.discovery import RawJob
from app.database.models import Job, JobStatus, JobSourceProvenance, JobVersion, Source
from app.canonicalization.normalize import (
    normalize_title,
    normalize_company,
    normalize_location,
    normalize_url
)
from app.canonicalization.identity import resolve_identity

def process_raw_job(db: Session, raw_job: RawJob) -> Tuple[str, Job]:
    """
    Core canonicalization transaction.
    Takes a RawJob, resolves its identity, and idempotently upserts it into the database.
    Returns a tuple of (ResolutionResult, Job).
    ResolutionResult: "NEW", "SAME", "UPDATED"
    """
    # 1. Identity Resolution
    existing_job = resolve_identity(db, raw_job)
    
    if not existing_job:
        # Create New Job
        norm_title = normalize_title(raw_job.title)
        norm_company = normalize_company(raw_job.company)
        norm_location = normalize_location(raw_job.location)
        norm_apply = normalize_url(raw_job.provenance.apply_url) if raw_job.provenance.apply_url else normalize_url(raw_job.provenance.source_url)
        
        job = Job(
            title=norm_title or raw_job.title,
            company_name=norm_company or raw_job.company,
            location=norm_location or raw_job.location,
            canonical_apply_url=norm_apply,
            description=raw_job.description,
            job_type=raw_job.employment_type,
            remote_status=raw_job.remote_status,
            status=JobStatus.ACTIVE,
            last_source_seen_at=raw_job.discovered_at
        )
        db.add(job)
        db.flush() # get ID
        
        # Determine Source ID (if source domain exists)
        source_domain = None
        if raw_job.provenance.source_type == "direct_ats":
            # Very simplistic for now, relying on DomainPolicy or existing tables in a real app
            # For simplicity, we just use the raw target url's domain if we have it
            # In Job-Claw, we might need to lookup `Source` table by domain
            pass
            
        # Create Provenance
        prov = JobSourceProvenance(
            job_id=job.id,
            source_id=raw_job.provenance.source_id,
            source_type=raw_job.provenance.source_type,
            source_job_id=raw_job.provenance.source_job_id,
            source_url=normalize_url(raw_job.provenance.source_url),
            raw_payload=raw_job.provider_metadata,
            observed_at=raw_job.discovered_at
        )
        db.add(prov)
        
        # Initial Version creation not strictly necessary unless we want the very first snapshot,
        # but the spec says "Do not create meaningless versions for identical data". 
        # A brand new job is just the canonical record.
        
        db.commit()
        db.refresh(job)
        return "NEW", job
        
    else:
        # We found an existing job
        result = "SAME"
        
        # 2. Check if we need to update lifecycle
        if existing_job.status in (JobStatus.EXPIRED, JobStatus.STALE, JobStatus.UNKNOWN):
            existing_job.status = JobStatus.ACTIVE
            result = "UPDATED"
            
        last_seen = existing_job.last_source_seen_at
        if last_seen and last_seen.tzinfo is None:
            from datetime import timezone
            last_seen = last_seen.replace(tzinfo=timezone.utc)
            
        if not last_seen or raw_job.discovered_at > last_seen:
            existing_job.last_source_seen_at = raw_job.discovered_at
            
        # 3. Check for Provenance deduplication
        norm_source_url = normalize_url(raw_job.provenance.source_url)
        prov_exists = False
        for prov in existing_job.provenances:
            obs_at = prov.observed_at
            if obs_at and obs_at.tzinfo is None:
                from datetime import timezone
                obs_at = obs_at.replace(tzinfo=timezone.utc)
                
            if (prov.source_job_id == raw_job.provenance.source_job_id and 
                prov.source_id == raw_job.provenance.source_id and 
                prov.source_type == raw_job.provenance.source_type):
                prov_exists = True
                # Update observation time
                if obs_at is None or raw_job.discovered_at > obs_at:
                    prov.observed_at = raw_job.discovered_at
                break
                
        if not prov_exists:
            new_prov = JobSourceProvenance(
                job_id=existing_job.id,
                source_id=raw_job.provenance.source_id,
                source_type=raw_job.provenance.source_type,
                source_job_id=raw_job.provenance.source_job_id,
                source_url=norm_source_url,
                raw_payload=raw_job.provider_metadata,
                observed_at=raw_job.discovered_at
            )
            db.add(new_prov)
            
        # 4. Check for meaningful version changes
        changed_fields = []
        old_state = {}
        new_state = {}
        
        # We only check fields that matter: title, description, location, remote_status
        norm_title = normalize_title(raw_job.title) or raw_job.title
        norm_location = normalize_location(raw_job.location) or raw_job.location
        
        if existing_job.title != norm_title:
            changed_fields.append("title")
            old_state["title"] = existing_job.title
            new_state["title"] = norm_title
            existing_job.title = norm_title
            
        if existing_job.location != norm_location:
            changed_fields.append("location")
            old_state["location"] = existing_job.location
            new_state["location"] = norm_location
            existing_job.location = norm_location
            
        if raw_job.description and existing_job.description != raw_job.description:
            # Basic equality check, could be a hashing check for large text
            changed_fields.append("description")
            old_state["description"] = "..." # Truncated to avoid massive JSON
            new_state["description"] = "..."
            existing_job.description = raw_job.description
            
        if changed_fields:
            result = "UPDATED"
            version = JobVersion(
                job_id=existing_job.id,
                changed_fields=changed_fields,
                previous_state=old_state,
                new_state=new_state
            )
            db.add(version)
            
        try:
            db.commit()
            db.refresh(existing_job)
        except IntegrityError:
            db.rollback()
            raise
            
        return result, existing_job

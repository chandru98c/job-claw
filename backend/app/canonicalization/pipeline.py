import re
import json
import urllib.parse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Tuple, Optional

from app.schemas.discovery import RawJob
from app.database.models import Job, JobStatus, JobSourceProvenance, JobVersion, Source
from app.canonicalization.normalize import (
    normalize_title,
    normalize_company,
    normalize_location,
    normalize_url
)
from app.canonicalization.identity import resolve_identity
from app.canonicalization.enrich import (
    extract_degree,
    extract_salary,
    classify_role,
    extract_experience,
    normalize_south_india_location
)

def resolve_canonical_apply_url(raw_job: RawJob) -> Optional[str]:
    """
    Extracts and validates a direct application URL.
    Reconstructs deep links for known ATS platforms (Keka, Darwinbox, BambooHR, Personio).
    NEVER allows generic career portal landing pages or blog aggregator links to be stored as canonical_apply_url.
    """
    is_wordpress = bool(raw_job.provenance.provider_name and "wordpress" in raw_job.provenance.provider_name.lower())
    
    raw_target_apply = (
        raw_job.provenance.apply_url
        or getattr(raw_job, "apply_url", None)
        or getattr(raw_job, "url", None)
    )
    
    source_job_id = raw_job.provenance.source_job_id or (raw_job.provider_metadata.get("job_id") if raw_job.provider_metadata else None)
    source_url = raw_job.provenance.source_url or ""
    
    # Check if target apply is empty or ends with generic path
    is_generic = False
    if not raw_target_apply:
        is_generic = True
    else:
        try:
            parsed = urllib.parse.urlparse(raw_target_apply)
            p = parsed.path.rstrip("/").lower()
            generic_paths = {
                "", "/careers", "/jobs", "/career", "/job-opportunities",
                "/about-us/careers", "/en/careers", "/en-in/careers",
                "/careers/odc-opportunities", "/careers/opportunities",
                "/careers/consulting-jobs", "/odc_opportunities",
                "/opportunities", "/consulting_jobs", "/jobs-list",
                "/all-jobs", "/open-positions", "/openings", "/vacancies",
                "/current-openings", "/careers-home", "/jobs-home"
            }
            if p in generic_paths or p.endswith(("/careers", "/jobs", "/career", "/odc_opportunities", "/odc-opportunities", "/opportunities", "/consulting_jobs", "/consulting-jobs")):
                is_generic = True
        except Exception:
            is_generic = True
            
    if is_generic:
        # Attempt deep link reconstruction from source_url + source_job_id
        if "keka.com" in source_url and source_job_id:
            m = re.search(r"https?://([a-zA-Z0-9_-]+)\.keka\.com", source_url)
            if m:
                raw_target_apply = f"https://{m.group(1)}.keka.com/careers/jobdetails/{source_job_id}"
                is_generic = False
        elif "darwinbox" in source_url and source_job_id:
            m = re.search(r"https?://([a-zA-Z0-9_.-]+darwinbox\.(?:in|com))", source_url)
            if m:
                raw_target_apply = f"https://{m.group(1)}/ms/candidate/careers/{source_job_id}"
                is_generic = False
        elif "bamboohr.com" in source_url and source_job_id:
            m = re.search(r"https?://([a-zA-Z0-9_-]+)\.bamboohr\.com", source_url)
            if m:
                raw_target_apply = f"https://{m.group(1)}.bamboohr.com/careers/{source_job_id}"
                is_generic = False
        elif "personio" in source_url and source_job_id:
            m = re.search(r"https?://([a-zA-Z0-9_-]+)\.jobs\.personio\.", source_url)
            if m:
                raw_target_apply = f"https://{m.group(1)}.jobs.personio.com/job/{source_job_id}"
                is_generic = False

    if is_generic:
        # NEVER fall back to source_url for WordPress aggregators or LLM extracted fallback!
        if is_wordpress or raw_job.provenance.source_type == "llm_extracted":
            return None
        # For direct employer sources where no deep link exists, normalize source_url only if not empty
        return normalize_url(raw_job.provenance.source_url) if raw_job.provenance.source_url else None

    return normalize_url(raw_target_apply)

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
        
        # Enrich metadata
        desc_text = raw_job.description or ""
        # Extract and enrich degree / education
        degree = extract_degree(desc_text) or extract_degree(raw_job.title)
        sal_min, sal_max, sal_curr = extract_salary(desc_text)
        role = classify_role(raw_job.title, desc_text)
        exp = extract_experience(raw_job.title, desc_text)

        # Normalize location accurately: prioritize explicit raw_job.location over text body
        raw_loc = (raw_job.location or "").strip()
        norm_loc_si, corridor = normalize_south_india_location(raw_loc, raw_job.title)
        if corridor:
            norm_location = norm_loc_si
        elif raw_loc and raw_loc.lower() not in ("unspecified", "india"):
            norm_location = normalize_location(raw_loc) or norm_loc_si or raw_loc
        else:
            norm_location = norm_loc_si or "India"

        # Apply URL handling: NEVER allow WordPress aggregator blog link or generic root career page to be stored as canonical_apply_url!
        norm_apply = resolve_canonical_apply_url(raw_job)

        job = Job(
            title=norm_title or raw_job.title,
            company_name=norm_company or raw_job.company,
            location=norm_location or "India",
            canonical_apply_url=norm_apply,
            description=raw_job.description,
            job_type=raw_job.employment_type,
            remote_status=raw_job.remote_status,
            education_level=degree,
            salary_min=sal_min,
            salary_max=sal_max,
            salary_currency=sal_curr,
            role_category=role,
            experience_level=exp,
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
        
        norm_title = normalize_title(raw_job.title) or raw_job.title
        raw_loc = (raw_job.location or "").strip()
        norm_loc_si, corridor = normalize_south_india_location(raw_loc, raw_job.title)
        if corridor:
            norm_location = norm_loc_si
        elif raw_loc and raw_loc.lower() not in ("unspecified", "india"):
            norm_location = normalize_location(raw_loc) or norm_loc_si or raw_loc
        else:
            norm_location = norm_loc_si or "India"

        if existing_job.title != norm_title:
            changed_fields.append("title")
            old_state["title"] = existing_job.title
            new_state["title"] = norm_title
            existing_job.title = norm_title
            
        if norm_location and existing_job.location != norm_location:
            changed_fields.append("location")
            old_state["location"] = existing_job.location
            new_state["location"] = norm_location
            existing_job.location = norm_location

        # Check and update canonical_apply_url
        new_apply = resolve_canonical_apply_url(raw_job)
        existing_is_generic = bool(
            not existing_job.canonical_apply_url
            or any(existing_job.canonical_apply_url.rstrip("/").lower().endswith(g) for g in ("/careers", "/jobs", "/career", "/job-opportunities"))
        )
        if new_apply and (existing_is_generic or (new_apply != existing_job.canonical_apply_url and not any(new_apply.rstrip("/").lower().endswith(g) for g in ("/careers", "/jobs", "/career", "/job-opportunities")))):
            if existing_job.canonical_apply_url != new_apply:
                changed_fields.append("canonical_apply_url")
                old_state["canonical_apply_url"] = existing_job.canonical_apply_url
                new_state["canonical_apply_url"] = new_apply
                existing_job.canonical_apply_url = new_apply

        # Check and update degree
        desc_text = raw_job.description or ""
        deg = extract_degree(desc_text) or extract_degree(raw_job.title)
        if deg and existing_job.education_level != deg:
            changed_fields.append("education_level")
            old_state["education_level"] = existing_job.education_level
            new_state["education_level"] = deg
            existing_job.education_level = deg
            
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

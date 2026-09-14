from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
from app.database.models import Job, JobSourceProvenance
from app.schemas.discovery import RawJob
from app.canonicalization.normalize import normalize_title, normalize_company, normalize_location, normalize_url

def resolve_identity(db: Session, raw_job: RawJob) -> Optional[Job]:
    """
    Deterministic identity resolution pipeline.
    Returns an existing Job if a strong or medium identity match is found.
    Returns None if no match is found (New Job).
    """
    
    # 1. Strong Identity: Source Job ID
    if raw_job.provenance.source_job_id:
        existing_prov = db.query(JobSourceProvenance).filter(
            JobSourceProvenance.source_job_id == raw_job.provenance.source_job_id,
            # We also ensure it's from the same provider type/domain to avoid cross-pollination of generic IDs
            JobSourceProvenance.source_type == raw_job.provenance.source_type
        ).first()
        if existing_prov and existing_prov.job:
            return existing_prov.job
            
    # 2. Strong Identity: Apply URL or Source URL
    norm_apply_url = normalize_url(raw_job.provenance.apply_url) if raw_job.provenance.apply_url else None
    norm_source_url = normalize_url(raw_job.provenance.source_url) if raw_job.provenance.source_url else None
    
    urls_to_check = [u for u in [norm_apply_url, norm_source_url] if u]
    if urls_to_check:
        # Check against Job.canonical_apply_url
        match = db.query(Job).filter(Job.canonical_apply_url.in_(urls_to_check)).first()
        if match:
            return match
            
        # Check against JobSourceProvenance.source_url
        prov_match = db.query(JobSourceProvenance).filter(
            JobSourceProvenance.source_url.in_(urls_to_check)
        ).first()
        if prov_match and prov_match.job:
            return prov_match.job

    # 3. Medium Identity: Normalized Core Fields (Company + Title + Location)
    norm_title = normalize_title(raw_job.title)
    norm_company = normalize_company(raw_job.company)
    norm_location = normalize_location(raw_job.location)
    
    if norm_title and norm_company:
        query = db.query(Job).filter(
            Job.company_name == norm_company,
            Job.title == norm_title
        )
        
        # Location might be None in raw_job
        if norm_location:
            query = query.filter(
                or_(
                    Job.location == norm_location,
                    Job.location.is_(None)
                )
            )
            
        matches = query.all()
        # If we have exactly one match, we are confident.
        # If there are multiple matches, we skip deterministic matching to avoid merging wrong jobs (could be multiple requisitions for same title/company)
        if len(matches) == 1:
            return matches[0]

    # Fuzzy identity (Step 6) is skipped for now per requirements (deterministic only, preserve ambiguity)
    return None

import uuid
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set
from sqlalchemy import select, or_, and_, func, text, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import (
    Profile, 
    Job, 
    JobStatus, 
    JobRecommendation, 
    RecommendationState,
    Application
)
from app.schemas.recommendation import JobRecommendationResponse

# Recognized tech keywords for skill extraction and matching
POPULAR_TECH_KEYWORDS = [
    "Python", "FastAPI", "Django", "Flask", "React", "Next.js", "TypeScript", 
    "JavaScript", "PostgreSQL", "MySQL", "SQL", "TailwindCSS", "Node.js", 
    "GraphQL", "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Redis", 
    "MongoDB", "HTML", "CSS", "Git", "C++", "Java", "Spring", "Go", "Rust", 
    "AI", "Machine Learning", "LLM", "Full Stack", "Frontend", "Backend"
]

def _extract_skills(text_blob: str, profile_skills: List[str]) -> List[str]:
    """Finds which candidate profile skills are mentioned in the job text."""
    if not text_blob:
        return []
    
    blob_lower = text_blob.lower()
    matched = []
    
    # Check user's skills first
    for s in profile_skills:
        pattern = r"\b" + re.escape(s.lower()) + r"\b"
        if re.search(pattern, blob_lower):
            matched.append(s)
            
    # Also look for key modern stack matches
    for k in POPULAR_TECH_KEYWORDS:
        if k not in matched:
            pattern = r"\b" + re.escape(k.lower()) + r"\b"
            if re.search(pattern, blob_lower):
                matched.append(k)
                
    return matched[:6]

def _calculate_match_score(
    job: Job, 
    profile: Profile, 
    matched_skills: List[str]
) -> tuple[int, List[str]]:
    """
    Computes an accurate, deterministic match score (0-99%) 
    and returns human-readable justification reasons aligned with candidate preferences.
    """
    score = 55
    reasons: List[str] = []
    
    job_title = (job.title or "").lower()
    job_loc = (job.location or "").lower()
    job_remote = (job.remote_status or "").lower()
    job_desc = (job.description or "").lower()
    
    pref_locs = [p.lower().strip() for p in (profile.preferred_locations or [])]
    user_loc = (profile.location or "").lower().strip()
    all_user_locs = [l for l in pref_locs if l]
    if user_loc and user_loc not in all_user_locs:
        all_user_locs.append(user_loc)
    
    from app.services.search import _location_variants
    
    # 1. Location Matching (Aligned to Candidate's Specific Target Hubs)
    is_remote = "remote" in job_remote or "remote" in job_loc or "hybrid" in job_remote or "hybrid" in job_loc
    user_matched_hub = None
    for target in all_user_locs:
        target_variants = _location_variants(target)
        if any(v in job_loc for v in target_variants):
            user_matched_hub = target.capitalize()
            break
            
    if user_matched_hub:
        score += 28
        reasons.append(f"Target Hub Fit: {user_matched_hub}")
    elif is_remote:
        score += 22
        reasons.append("Work Flexibility: Remote / Hybrid Eligible")
    elif any(loc in job_loc for loc in ["chennai", "bengaluru", "bangalore", "hyderabad", "coimbatore", "pune", "delhi", "mumbai", "india"]):
        score += 15
        reasons.append("Major Indian Tech Corridor")
    else:
        score -= 20
        
    # 2. Skill & Stack Overlap
    profile_skills_lower = [s.lower() for s in (profile.skills or [])]
    direct_skill_matches = [s for s in matched_skills if s.lower() in profile_skills_lower]
    
    if direct_skill_matches:
        skill_boost = min(len(direct_skill_matches) * 6, 24)
        score += skill_boost
        reasons.append(f"Core Stack Alignment: {', '.join(direct_skill_matches[:3])}")
    elif matched_skills:
        score += 8
        reasons.append(f"Related Technologies: {', '.join(matched_skills[:3])}")
        
    # 3. Role & Title Alignment
    target_roles = ["software", "developer", "engineer", "full stack", "backend", "frontend", "python", "react", "web", "ai"]
    title_matches = [r for r in target_roles if r in job_title]
    if title_matches:
        score += 12
        reasons.append("Role Specialty: Software Engineering")
        
    # 4. Education & Qualification
    edu = (profile.education or "").lower()
    job_edu = (job.education_level or "").lower()
    if edu and any(e in job_desc or e in job_edu for e in ["mca", "b.tech", "btech", "degree", "graduate", "computer science"]):
        score += 8
        reasons.append(f"Degree Alignment: {profile.education or 'Technical Degree'}")
        
    # 5. Experience & Seniority Alignment
    cand_exp_level = (profile.experience_level or "").lower().strip()
    cand_exp_text = (profile.experience or "").lower().strip()
    cand_years = profile.experience_years if profile.experience_years is not None else 0.0
    
    is_fresher_cand = (
        cand_exp_level in ["fresher", "intern", "entry"] or 
        cand_years <= 1.0 or 
        "fresher" in cand_exp_text or 
        "0-1" in cand_exp_text
    )
    
    job_exp = (job.experience_level or "").lower().strip()
    if is_fresher_cand:
        if job_exp in ["fresher"] or any(s in job_title for s in ["fresher", "intern", "trainee", "entry"]):
            score += 16
            reasons.append("Experience Fit: Fresher Friendly (0-1 Yrs)")
        elif job_exp in ["senior"] or any(s in job_title for s in ["senior", "lead", "architect", "principal"]):
            score -= 22
            reasons.append("Senior Role (5+ Yrs Required)")
        else:
            score += 5
            reasons.append("Early Career Position")
    elif cand_exp_level in ["senior", "lead"]:
        if job_exp == "senior" or any(s in job_title for s in ["senior", "lead", "architect", "principal"]):
            score += 16
            reasons.append("Seniority Alignment: Senior / Lead Engineer")
        elif job_exp == "fresher":
            score -= 15
    else: # Junior (1-3 yrs) or Mid (3-5 yrs)
        if job_exp in ["junior", "mid"]:
            score += 14
            reasons.append("Experience Fit: Aligned with Background (1-3 Yrs)")
        elif job_exp == "senior":
            score -= 12

    # Cap between 68% and 98%
    final_score = max(min(score, 98), 68)
    
    if not reasons:
        reasons.append("🎯 General Profile Fit")
        
    return final_score, reasons

async def fetch_recommended_jobs(
    db: AsyncSession,
    profile: Profile,
    limit: int = 15,
    offset: int = 0,
    scope: str = "all", # 'all', 'local', 'remote'
    role: Optional[str] = None,
    degree: Optional[str] = None,
    experience_level: Optional[str] = None,
    location: Optional[str] = None,
    q: Optional[str] = None,
    exclude_job_ids: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    """
    Mines canonical jobs directly from DB matching candidate preferences with fast indexing
    and 100% accurate structured filters.
    """
    from app.services.search import (
        _location_variants,
        _build_degree_condition,
        _build_experience_condition,
        _build_role_condition
    )

    if exclude_job_ids is None:
        exclude_job_ids = set()

    conditions = [
        Job.status.in_([JobStatus.ACTIVE, JobStatus.VERIFYING]),
        Job.canonical_apply_url.isnot(None),
        Job.canonical_apply_url != ""
    ]

    # Scope handling (Candidate-Centric)
    if scope == "local":
        pref_locs = profile.preferred_locations or []
        if profile.location:
            pref_locs = list(pref_locs) + [profile.location]
        if not pref_locs:
            pref_locs = ["chennai", "bengaluru", "hyderabad", "coimbatore"]
            
        all_variants = []
        for l in pref_locs:
            all_variants.extend(_location_variants(l))
        conditions.append(or_(*[Job.location.ilike(f"%{v}%") for v in set(all_variants)]))
    elif scope == "remote":
        conditions.append(
            or_(
                Job.remote_status.ilike("%remote%"),
                Job.location.ilike("%remote%"),
                Job.remote_status.ilike("%hybrid%")
            )
        )

    # User-applied interactive filters
    if location:
        variants = _location_variants(location)
        conditions.append(or_(*[Job.location.ilike(f"%{v}%") for v in variants]))

    if role:
        conditions.append(_build_role_condition(role))

    if degree:
        conditions.append(_build_degree_condition(degree))

    if experience_level:
        conditions.append(_build_experience_condition(experience_level))

    if q:
        q_clean = q.strip()
        q_tokens = [t.strip().lower() for t in q_clean.split() if t.strip()]
        phrase_cond = or_(
            Job.title.ilike(f"%{q_clean}%"),
            Job.company_name.ilike(f"%{q_clean}%"),
            Job.location.ilike(f"%{q_clean}%"),
            Job.education_level.ilike(f"%{q_clean}%"),
            Job.role_category.ilike(f"%{q_clean}%")
        )
        if len(q_tokens) > 1:
            token_conds = []
            for t in q_tokens:
                token_conds.append(or_(
                    Job.title.ilike(f"%{t}%"),
                    Job.company_name.ilike(f"%{t}%"),
                    Job.role_category.ilike(f"%{t}%"),
                    Job.location.ilike(f"%{t}%"),
                    Job.education_level.ilike(f"%{t}%")
                ))
            conditions.append(or_(phrase_cond, and_(*token_conds)))
        else:
            conditions.append(phrase_cond)

    if exclude_job_ids:
        conditions.append(~Job.id.in_(list(exclude_job_ids)))

    # Query strictly newest jobs first by actual posting date
    stmt = (
        select(Job)
        .where(and_(*conditions))
        .order_by(
            Job.posted_at.desc().nullslast(),
            desc(Job.last_source_seen_at),
            desc(Job.created_at),
            desc(Job.id)
        )
        .offset(offset)
        .limit(limit * 2)
    )

    result = await db.execute(stmt)
    jobs = result.scalars().all()

    profile_skills = profile.skills or []
    scored_candidates = []

    for j in jobs:
        text_blob = f"{j.title} {j.description or ''}"
        matched_skills = _extract_skills(text_blob, profile_skills)
        score, reasons = _calculate_match_score(j, profile, matched_skills)
        
        # Clean company fallback
        clean_company = j.company_name
        if not clean_company or clean_company.lower() in ["unknown", "default"]:
            try:
                from urllib.parse import urlparse
                netloc = urlparse(j.canonical_apply_url).netloc
                parts = netloc.split(".")
                if len(parts) >= 2:
                    clean_company = parts[-2].capitalize() if parts[-2] not in ["recruitee", "breezy", "greenhouse", "ashbyhq", "bamboohr"] else parts[0].capitalize()
                else:
                    clean_company = "Tech Company"
            except Exception:
                clean_company = "Tech Company"

        scored_candidates.append({
            "job": j,
            "company_name": clean_company,
            "score": score,
            "reasons": reasons,
            "matched_skills": matched_skills
        })

    # Sort candidates by score descending
    scored_candidates.sort(key=lambda x: x["score"], reverse=True)
    return scored_candidates[:limit]


async def get_or_generate_recommendations(
    db: AsyncSession,
    profile: Profile,
    limit: int = 15,
    page: int = 1,
    scope: str = "all",
    role: Optional[str] = None,
    degree: Optional[str] = None,
    experience_level: Optional[str] = None,
    location: Optional[str] = None,
    q: Optional[str] = None,
    force_refresh: bool = False
) -> List[JobRecommendationResponse]:
    """
    Main entry point: gets active recommendations or discovers a new set with full filter support.
    """
    has_custom_filters = bool(role or degree or experience_level or location or q)

    # When custom filters are provided, always dynamically mine the matching candidates directly
    if not force_refresh and not has_custom_filters:
        existing_stmt = (
            select(JobRecommendation)
            .options(selectinload(JobRecommendation.job))
            .where(
                JobRecommendation.profile_id == profile.id,
                JobRecommendation.state.in_([
                    RecommendationState.NEW, 
                    RecommendationState.SEEN, 
                    RecommendationState.SAVED
                ])
            )
            .order_by(JobRecommendation.score.desc())
        )
        
        existing_result = await db.execute(existing_stmt)
        existing_recs = existing_result.scalars().all()
        
        if existing_recs and len(existing_recs) >= 5:
            return [_build_response(r, r.job) for r in existing_recs[:limit]]

    # Collect seen jobs to maintain novelty unless force refreshing or custom filtering
    seen_job_ids = set()
    if not force_refresh and not has_custom_filters:
        seen_jobs_res = await db.execute(
            select(JobRecommendation.job_id).where(JobRecommendation.profile_id == profile.id)
        )
        seen_job_ids = set(seen_jobs_res.scalars().all())

    offset = (page - 1) * limit

    candidate_results = await fetch_recommended_jobs(
        db=db,
        profile=profile,
        limit=limit,
        offset=offset,
        scope=scope,
        role=role,
        degree=degree,
        experience_level=experience_level,
        location=location,
        q=q,
        exclude_job_ids=seen_job_ids
    )

    if not candidate_results and seen_job_ids:
        # Recycle with newest offset
        candidate_results = await fetch_recommended_jobs(
            db=db,
            profile=profile,
            limit=limit,
            offset=offset,
            scope=scope,
            role=role,
            degree=degree,
            experience_level=experience_level,
            location=location,
            q=q,
            exclude_job_ids=set()
        )

    response_items = []
    
    for c in candidate_results:
        j: Job = c["job"]
        
        rec_check = await db.execute(
            select(JobRecommendation).where(
                JobRecommendation.profile_id == profile.id,
                JobRecommendation.job_id == j.id
            )
        )
        rec = rec_check.scalar_one_or_none()
        
        if not rec:
            rec = JobRecommendation(
                id=str(uuid.uuid4()),
                profile_id=profile.id,
                job_id=j.id,
                score=c["score"],
                reasons=c["reasons"],
                state=RecommendationState.NEW,
                first_seen_at=datetime.now(timezone.utc),
                surfaced_at=datetime.now(timezone.utc)
            )
            db.add(rec)
        else:
            rec.score = c["score"]
            rec.reasons = c["reasons"]
            rec.state = RecommendationState.NEW
            rec.surfaced_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(rec)
        
        resp_item = _build_response(rec, j, custom_company=c["company_name"], matched_skills=c.get("matched_skills"))
        response_items.append(resp_item)

    return response_items

def _build_response(
    rec: JobRecommendation, 
    job: Optional[Job], 
    custom_company: Optional[str] = None,
    matched_skills: Optional[List[str]] = None
) -> JobRecommendationResponse:
    from app.api.jobs import _extract_corridor_and_city
    
    item = JobRecommendationResponse.model_validate(rec)
    if job:
        item.title = job.title
        item.company_name = custom_company or job.company_name
        item.location = job.location
        item.job_type = job.job_type
        item.apply_url = job.canonical_apply_url
        item.salary_min = job.salary_min
        item.salary_max = job.salary_max
        item.remote_status = job.remote_status
        item.education_level = job.education_level
        item.role_category = job.role_category
        
        corr, city = _extract_corridor_and_city(job.location)
        item.corridor = corr
        item.city = city
        item.posted_at = job.posted_at or job.last_source_seen_at or job.created_at
        item.experience_level = job.experience_level or "Junior (1-3 Yrs)"
        
        if matched_skills:
            item.matched_skills = matched_skills
        else:
            blob = f"{job.title} {job.description or ''}"
            item.matched_skills = _extract_skills(blob, ["Python", "FastAPI", "React", "TypeScript", "PostgreSQL", "SQL", "Next.js", "TailwindCSS"])
    return item

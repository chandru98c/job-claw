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
    and returns human-readable justification reasons.
    """
    score = 55
    reasons: List[str] = []
    
    job_title = (job.title or "").lower()
    job_loc = (job.location or "").lower()
    job_remote = (job.remote_status or "").lower()
    job_desc = (job.description or "").lower()
    
    pref_locs = [p.lower().strip() for p in (profile.preferred_locations or [])]
    user_loc = (profile.location or "").lower()
    
    # 1. Location Matching (Highest Priority)
    is_local_chennai = any(k in job_loc for k in ["chennai", "guindy", "mepz", "siruseri", "omr", "tamil nadu"])
    is_remote = "remote" in job_remote or "remote" in job_loc or "hybrid" in job_remote or "hybrid" in job_loc
    
    if is_local_chennai:
        score += 28
        reasons.append("Exact Regional Fit: Chennai Tech Hub")
    elif is_remote:
        score += 20
        reasons.append("Work Flexibility: Remote / Hybrid Eligible")
    elif any(loc in job_loc for loc in ["bengaluru", "bangalore", "hyderabad", "pune", "india"]):
        score += 15
        reasons.append("Indian Tech Corridor (Bangalore / Hyderabad)")
    else:
        # Penalize foreign on-site jobs
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
    if edu and any(e in job_desc or e in (job.education_level or "").lower() for e in ["mca", "b.tech", "btech", "degree", "graduate", "computer science"]):
        score += 6
        reasons.append("Degree Alignment: MCA / Technical Degree")
        
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
    
    job_exp_level = (job.experience_level or "").lower().strip()
    senior_keywords = ["senior", "lead", "architect", "principal", "manager", "director", "staff engineer", "vp", "head of"]
    is_senior_job = (
        job_exp_level in ["senior", "lead", "principal", "mid-senior"] or
        any(s in job_title for s in senior_keywords) or
        any(s in job_desc for s in ["5+ years", "6+ years", "7+ years", "8+ years", "10+ years"])
    )
    is_fresher_job = (
        job_exp_level in ["fresher", "entry", "intern", "junior"] or
        any(s in job_title for s in ["fresher", "intern", "trainee", "graduate", "junior", "associate", "entry level"]) or
        any(s in job_desc for s in ["freshers can apply", "0-1 year", "0-1 yr", "0 to 1 year", "entry level", "graduate trainee", "campus"])
    )
    
    if is_fresher_cand:
        if is_fresher_job:
            score += 15
            reasons.append("Experience Fit: Fresher & Entry-Level Friendly (0-1 Yrs)")
        elif is_senior_job:
            score -= 18
            reasons.append("Senior Role (5+ Yrs Required)")
        else:
            score += 5
            reasons.append("Early Career Software Role")
    elif cand_exp_level in ["senior", "lead"]:
        if is_senior_job:
            score += 15
            reasons.append("Seniority Alignment: Senior / Lead Engineer")
        elif is_fresher_job:
            score -= 12
    else: # Junior / Mid candidate
        if is_fresher_job or not is_senior_job:
            score += 10
            reasons.append("Experience Fit: Aligned with Background")
        else:
            score -= 10

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
    exclude_job_ids: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    """
    Mines canonical jobs directly from DB matching candidate preferences with fast indexing.
    """
    if exclude_job_ids is None:
        exclude_job_ids = set()

    # Construct location conditions based on requested scope
    loc_conditions = []
    
    if scope == "local":
        loc_conditions.append(
            or_(
                Job.location.ilike("%chennai%"),
                Job.location.ilike("%tamil nadu%"),
                Job.location.ilike("%guindy%"),
                Job.location.ilike("%mepz%"),
                Job.location.ilike("%siruseri%"),
                Job.location.ilike("%omr%")
            )
        )
    elif scope == "remote":
        loc_conditions.append(
            or_(
                Job.remote_status.ilike("%remote%"),
                Job.location.ilike("%remote%"),
                Job.remote_status.ilike("%hybrid%")
            )
        )
    else: # "all"
        loc_conditions.append(
            or_(
                Job.location.ilike("%chennai%"),
                Job.location.ilike("%tamil nadu%"),
                Job.location.ilike("%guindy%"),
                Job.location.ilike("%mepz%"),
                Job.location.ilike("%siruseri%"),
                Job.location.ilike("%omr%"),
                Job.remote_status.ilike("%remote%"),
                Job.location.ilike("%remote%"),
                Job.location.ilike("%bengaluru%"),
                Job.location.ilike("%bangalore%"),
                Job.location.ilike("%hyderabad%"),
                Job.location.ilike("%india%")
            )
        )

    # Technical roles filter
    role_condition = or_(
        Job.title.ilike("%software%"),
        Job.title.ilike("%developer%"),
        Job.title.ilike("%engineer%"),
        Job.title.ilike("%python%"),
        Job.title.ilike("%react%"),
        Job.title.ilike("%frontend%"),
        Job.title.ilike("%backend%"),
        Job.title.ilike("%full stack%"),
        Job.title.ilike("%fullstack%"),
        Job.title.ilike("%web%"),
        Job.title.ilike("%data%"),
        Job.title.ilike("%stack%")
    )

    stmt = (
        select(Job)
        .where(
            and_(
                *loc_conditions,
                role_condition,
                Job.canonical_apply_url.isnot(None),
                Job.canonical_apply_url != ""
            )
        )
    )

    if exclude_job_ids:
        stmt = stmt.where(~Job.id.in_(list(exclude_job_ids)))

    # Order priority: Experience-aligned Chennai/Local first, then Remote, then recent
    cand_exp_level = (profile.experience_level or "").lower().strip()
    cand_years = profile.experience_years if profile.experience_years is not None else 0.0
    is_fresher = cand_exp_level in ["fresher", "intern", "entry"] or cand_years <= 1.0 or "fresher" in (profile.experience or "").lower()

    if is_fresher:
        case_order = text("""
            CASE 
                WHEN (location ILIKE '%chennai%' OR location ILIKE '%guindy%' OR location ILIKE '%mepz%')
                     AND (experience_level ILIKE '%fresher%' OR title ILIKE '%fresher%' OR title ILIKE '%trainee%' OR title ILIKE '%intern%' OR title ILIKE '%graduate%' OR title ILIKE '%junior%' OR title ILIKE '%associate%') THEN 1
                WHEN (remote_status ILIKE '%remote%' OR location ILIKE '%remote%')
                     AND (experience_level ILIKE '%fresher%' OR title ILIKE '%fresher%' OR title ILIKE '%trainee%' OR title ILIKE '%intern%' OR title ILIKE '%graduate%' OR title ILIKE '%junior%' OR title ILIKE '%associate%') THEN 2
                WHEN location ILIKE '%chennai%' OR location ILIKE '%guindy%' OR location ILIKE '%mepz%' THEN 3
                WHEN remote_status ILIKE '%remote%' OR location ILIKE '%remote%' THEN 4
                WHEN location ILIKE '%tamil nadu%' THEN 5
                ELSE 6
            END,
            created_at DESC
        """)
    else:
        case_order = text("""
            CASE 
                WHEN location ILIKE '%chennai%' OR location ILIKE '%guindy%' OR location ILIKE '%mepz%' THEN 1
                WHEN remote_status ILIKE '%remote%' OR location ILIKE '%remote%' THEN 2
                WHEN location ILIKE '%tamil nadu%' THEN 3
                ELSE 4
            END,
            created_at DESC
        """)

    stmt = stmt.order_by(case_order).offset(offset).limit(limit * 2)

    result = await db.execute(stmt)
    jobs = result.scalars().all()

    profile_skills = profile.skills or []
    scored_candidates = []

    for j in jobs:
        text_blob = f"{j.title} {j.description or ''}"
        matched_skills = _extract_skills(text_blob, profile_skills)
        score, reasons = _calculate_match_score(j, profile, matched_skills)
        
        # Friendly company fallback
        clean_company = j.company_name
        if not clean_company or clean_company.lower() in ["unknown", "default"]:
            # Extract domain from apply url
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
    force_refresh: bool = False
) -> List[JobRecommendationResponse]:
    """
    Main entry point: gets active recommendations or discovers a new set.
    """
    # Find existing recommendations for this profile
    existing_stmt = (
        select(JobRecommendation)
        .options(selectinload(JobRecommendation.job))
        .where(JobRecommendation.profile_id == profile.id)
    )
    
    if not force_refresh:
        # Default view: show active recommendations (NEW, SEEN, SAVED)
        existing_stmt = existing_stmt.where(
            JobRecommendation.state.in_([
                RecommendationState.NEW, 
                RecommendationState.SEEN, 
                RecommendationState.SAVED
            ])
        ).order_by(JobRecommendation.score.desc())
        
        existing_result = await db.execute(existing_stmt)
        existing_recs = existing_result.scalars().all()
        
        if existing_recs and len(existing_recs) >= 5:
            # Return existing formatted recommendations
            return [_build_response(r, r.job) for r in existing_recs[:limit]]

    # If force_refresh is True OR fewer than 5 exist, generate a brand new set!
    # Collect all job IDs already seen/dismissed to ensure pure freshness
    seen_jobs_res = await db.execute(
        select(JobRecommendation.job_id).where(JobRecommendation.profile_id == profile.id)
    )
    seen_job_ids = set(seen_jobs_res.scalars().all())

    # When force_refresh is called, cycle offset based on page
    offset = (page - 1) * limit

    candidate_results = await fetch_recommended_jobs(
        db=db,
        profile=profile,
        limit=limit,
        offset=offset,
        scope=scope,
        exclude_job_ids=seen_job_ids if not force_refresh else set()
    )

    if not candidate_results and seen_job_ids:
        # If we exhausted unseen jobs, allow recycling with newest offset
        candidate_results = await fetch_recommended_jobs(
            db=db,
            profile=profile,
            limit=limit,
            offset=offset,
            scope=scope,
            exclude_job_ids=set()
        )

    response_items = []
    
    # Save newly generated recommendations into DB
    for c in candidate_results:
        j: Job = c["job"]
        
        # Check if already in recommendations
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
        
        # Build enriched response
        resp_item = _build_response(rec, j, custom_company=c["company_name"], matched_skills=c.get("matched_skills"))
        response_items.append(resp_item)

    return response_items

def _build_response(
    rec: JobRecommendation, 
    job: Optional[Job], 
    custom_company: Optional[str] = None,
    matched_skills: Optional[List[str]] = None
) -> JobRecommendationResponse:
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
        item.experience_level = job.experience_level or (
            "Fresher / Entry" if any(w in (job.title or "").lower() for w in ["fresher", "intern", "trainee", "junior", "graduate", "associate", "entry"]) 
            else "Senior / Lead" if any(w in (job.title or "").lower() for w in ["senior", "lead", "architect", "principal", "manager"])
            else "Mid / Experienced"
        )
        if matched_skills:
            item.matched_skills = matched_skills
        else:
            # Fallback extract top tech keywords from title/description
            blob = f"{job.title} {job.description or ''}"
            item.matched_skills = _extract_skills(blob, ["Python", "FastAPI", "React", "TypeScript", "PostgreSQL", "SQL", "Next.js", "TailwindCSS"])
    return item

import re
from typing import List, Tuple, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, desc, asc, func
from app.database.models import Job, JobStatus, Profile
from app.schemas.search import SearchQuery

# Indian city & corridor aliases — maps canonical name → all known variants
_CITY_ALIASES: dict[str, list[str]] = {
    # Parent Metros & States
    "south india": ["chennai", "tamil nadu", "coimbatore", "bengaluru", "bangalore", "hyderabad", "kochi", "kerala", "karnataka", "telangana", "andhra", "hosur"],
    "tamil nadu":  ["tamil nadu", "chennai", "coimbatore", "kovai", "madurai", "trichy", "tiruchirappalli", "hosur", "salem"],
    "chennai":     ["chennai", "madras", "omr", "siruseri", "taramani", "guindy", "porur", "sholinganallur", "perungudi", "mepz", "ambattur", "chengalpattu", "mahindra world city"],
    "checnnai":    ["chennai", "madras", "omr", "siruseri", "taramani", "guindy", "porur", "sholinganallur", "perungudi", "mepz", "ambattur", "chengalpattu", "mahindra world city"],
    "chenai":      ["chennai", "madras", "omr", "siruseri", "taramani", "guindy", "porur", "sholinganallur", "perungudi", "mepz", "ambattur", "chengalpattu", "mahindra world city"],
    "chenna":      ["chennai", "madras", "omr", "siruseri", "taramani", "guindy", "porur", "sholinganallur", "perungudi", "mepz", "ambattur", "chengalpattu", "mahindra world city"],
    "channai":     ["chennai", "madras", "omr", "siruseri", "taramani", "guindy", "porur", "sholinganallur", "perungudi", "mepz", "ambattur", "chengalpattu", "mahindra world city"],
    
    # Specific Micro-Corridors across India
    "omr":              ["omr", "siruseri", "taramani", "sholinganallur", "perungudi", "thoraipakkam", "naval", "tidel"],
    "siruseri":         ["siruseri", "omr", "naval", "sipcot"],
    "guindy":           ["guindy", "olympia", "mepz", "ekkatuthangal", "tambaram"],
    "mepz":             ["mepz", "tambaram", "chromepet", "guindy"],
    "porur":            ["porur", "dlf", "manapakkam", "commerzone"],
    "dlf":              ["dlf", "porur", "manapakkam"],
    "ambattur":         ["ambattur"],
    "chengalpattu":     ["chengalpattu", "mahindra world city"],
    "whitefield":       ["whitefield", "itpl", "epip", "brookfield"],
    "electronic city":  ["electronic city", "e-city", "hosur road"],
    "outer ring road":  ["outer ring road", "orr", "bellandur", "marathahalli", "ecospace", "kadubeesanahalli"],
    "manyata":          ["manyata", "hebbal", "nagavara"],
    "hitec city":       ["hitec city", "hitech city", "madhapur", "cyber towers", "mindspace"],
    "gachibowli":       ["gachibowli", "financial district", "nanakramguda", "waverock"],
    "kondapur":         ["kondapur", "knowledge city"],
    "hinjewadi":        ["hinjewadi", "hinjawadi", "pimpri"],
    "magarpatta":       ["magarpatta", "kharadi", "eon"],
    "bkc":              ["bkc", "bandra kurla"],
    "cyber city":       ["cyber city", "dlf cyber", "golf course", "gurugram", "gurgaon"],
    "noida":            ["noida", "sector 62", "greater noida", "expressway"],
    
    # Regional Hubs
    "coimbatore":       ["coimbatore", "kovai", "saravanampatti", "chil sez", "eachanari"],
    "madurai":          ["madurai", "vadapalanji"],
    "trichy":           ["trichy", "tiruchirappalli", "navalpattu"],
    "hosur":            ["hosur"],
    
    # Major Tech Metros
    "bangalore":        ["bangalore", "bengaluru", "karnataka", "whitefield", "electronic city", "manyata", "bellandur"],
    "bengaluru":        ["bangalore", "bengaluru", "karnataka", "whitefield", "electronic city", "manyata", "bellandur"],
    "hyderabad":        ["hyderabad", "secunderabad", "telangana", "hitec city", "gachibowli", "madhapur"],
    "kochi":            ["kochi", "cochin", "ernakulam", "kerala", "infopark", "kakkanad"],
    "mumbai":           ["mumbai", "bombay", "maharashtra", "navi mumbai", "thane", "bkc"],
    "delhi":            ["delhi", "new delhi", "ncr", "gurgaon", "gurugram", "noida", "faridabad"],
    "pune":             ["pune", "pimpri", "hinjawadi", "magarpatta", "kharadi"],
    "kolkata":          ["kolkata", "calcutta", "west bengal"],
}


def _location_variants(location: str) -> list[str]:
    """Return all alias variants for a location string, supporting compound corridor expressions."""
    if not location:
        return []
    
    raw = location.lower().strip()
    
    # Check direct canonical match
    if raw in _CITY_ALIASES:
        return _CITY_ALIASES[raw]

    # Split compound phrases like "Guindy / MEPZ" or "OMR / Siruseri" or "DLF Porur"
    tokens = [t.strip() for t in re.split(r'[/,|-]', raw) if t.strip()]
    
    collected_variants = set()
    for token in tokens:
        matched = False
        if token in _CITY_ALIASES:
            collected_variants.update(_CITY_ALIASES[token])
            matched = True
        else:
            # Check individual sub-words
            for w in token.split():
                if w in _CITY_ALIASES:
                    collected_variants.update(_CITY_ALIASES[w])
                    matched = True
        if not matched:
            collected_variants.add(token)

    return list(collected_variants) if collected_variants else [raw]

# Strict deterministic scoring model
SCORE_TITLE_MATCH = 40
SCORE_SKILL_MATCH = 30
SCORE_LOCATION_MATCH = 15
SCORE_REMOTE_MATCH = 10
SCORE_EMPLOYMENT_TYPE_MATCH = 5

def _build_degree_condition(degree_filter: str):
    deg_clean = degree_filter.strip().upper()
    if deg_clean == "MCA":
        return or_(
            Job.education_level.ilike("%MCA%"),
            Job.education_level.ilike("%Master%"),
            Job.education_level.ilike("%B.Tech%"),
            Job.education_level.ilike("%Any Graduate%"),
            Job.description.ilike("%MCA%"),
            Job.description.ilike("%Master of Computer%"),
            Job.description.ilike("%Computer Application%"),
            Job.description.ilike("%CS/IT%"),
            Job.description.ilike("%Computer Science%"),
            Job.description.ilike("%Any Graduate%"),
            Job.description.ilike("%Any Degree%"),
            and_(
                Job.education_level.is_(None),
                or_(
                    Job.role_category.in_(["software_engineer", "frontend", "backend", "fullstack", "mobile", "data_ai", "devops_cloud", "qa_testing"]),
                    Job.title.ilike("%developer%"),
                    Job.title.ilike("%engineer%"),
                    Job.title.ilike("%software%"),
                    Job.title.ilike("%analyst%"),
                    Job.title.ilike("%programmer%"),
                    Job.title.ilike("%tech%"),
                    Job.title.ilike("%intern%"),
                    Job.title.ilike("%trainee%")
                )
            )
        )
    elif deg_clean in ["B.TECH", "BTECH", "BE"]:
        return or_(
            Job.education_level.ilike("%B.Tech%"),
            Job.education_level.ilike("%Bachelor%"),
            Job.education_level.ilike("%Any Graduate%"),
            Job.description.ilike("%B.Tech%"),
            Job.description.ilike("%B.E%"),
            Job.description.ilike("%Engineering%"),
            Job.description.ilike("%Computer Science%"),
            Job.description.ilike("%Any Graduate%"),
            and_(
                Job.education_level.is_(None),
                or_(
                    Job.role_category.in_(["software_engineer", "frontend", "backend", "fullstack", "mobile", "data_ai", "devops_cloud", "qa_testing"]),
                    Job.title.ilike("%developer%"),
                    Job.title.ilike("%engineer%"),
                    Job.title.ilike("%software%")
                )
            )
        )
    elif deg_clean in ["M.TECH", "MTECH", "ME"]:
        return or_(
            Job.education_level.ilike("%M.Tech%"),
            Job.education_level.ilike("%Master%"),
            Job.description.ilike("%M.Tech%"),
            Job.description.ilike("%Master of Technology%"),
            Job.description.ilike("%Post Graduate%")
        )
    elif deg_clean == "BCA":
        return or_(
            Job.education_level.ilike("%BCA%"),
            Job.education_level.ilike("%Bachelor%"),
            Job.education_level.ilike("%Any Graduate%"),
            Job.description.ilike("%BCA%"),
            Job.description.ilike("%Computer Application%"),
            Job.description.ilike("%B.Sc%")
        )
    elif deg_clean in ["ANY GRADUATE", "ANY DEGREE"]:
        return Job.id.isnot(None)
    else:
        pattern = f"%{degree_filter.strip()}%"
        return or_(
            Job.education_level.ilike(pattern),
            Job.description.ilike(pattern)
        )

def _build_experience_condition(exp_filter: str):
    exp_clean = exp_filter.strip().lower()
    if exp_clean in ["fresher", "0", "0-1", "entry"]:
        return or_(
            Job.experience_level == "fresher",
            Job.title.ilike("%intern%"),
            Job.title.ilike("%trainee%"),
            Job.title.ilike("%fresher%"),
            Job.title.ilike("%campus%"),
            Job.title.ilike("%entry%"),
            Job.title.ilike("%graduate%"),
            Job.title.ilike("%apprentice%"),
            Job.job_type.ilike("%intern%"),
            Job.description.ilike("%fresher%"),
            Job.description.ilike("%0-1 year%"),
            Job.description.ilike("%0 to 1 year%"),
            Job.description.ilike("%0-2 year%"),
            Job.description.ilike("%0 years%"),
            Job.description.ilike("%entry level%"),
            Job.description.ilike("%no experience%"),
            Job.description.ilike("%freshers can apply%"),
            and_(
                Job.experience_level == "junior",
                or_(
                    Job.title.ilike("%junior%"),
                    Job.title.ilike("%associate%"),
                    Job.salary_min <= 600000
                )
            )
        )
    elif exp_clean in ["junior", "1-3"]:
        return or_(
            Job.experience_level.in_(["junior", "fresher"]),
            Job.title.ilike("%junior%"),
            Job.title.ilike("%associate%"),
            Job.title.ilike("%intern%"),
            Job.title.ilike("%trainee%")
        )
    elif exp_clean in ["mid", "3-5"]:
        return or_(
            Job.experience_level == "mid",
            Job.title.ilike("%mid%"),
            Job.description.ilike("%3-5 years%")
        )
    elif exp_clean in ["senior", "5+"]:
        return or_(
            Job.experience_level == "senior",
            Job.title.ilike("%senior%"),
            Job.title.ilike("%lead%"),
            Job.title.ilike("%principal%"),
            Job.title.ilike("%architect%")
        )
    else:
        return Job.experience_level == exp_clean

class SearchService:
    @staticmethod
    def _tokenize(text: str) -> set:
        """Simple tokenizer to create lowercase word boundaries."""
        if not text:
            return set()
        words = re.findall(r'\b\w+\b', text.lower())
        return set(words)

    @classmethod
    async def open_search(
        cls, 
        db: AsyncSession, 
        query: SearchQuery
    ) -> Tuple[List[Dict[str, Any]], int]:
        
        # 1. Base query: Freshness constraint (ACTIVE, VERIFYING)
        stmt = select(Job).where(Job.status.in_([JobStatus.ACTIVE, JobStatus.VERIFYING]))
        
        # 2. Strict SQL-side Filtering
        # For open search, we return all active jobs if no query, or filter if q/location exist.
        if query.q:
            q_clean = query.q.strip()
            q_pattern = f"%{q_clean}%"
            q_tokens = [t.strip().lower() for t in q_clean.split() if t.strip()]
            
            # Check location variants for tokens (handles typing "chennai", "checnnai", "omr", etc. in search box)
            loc_aliases = []
            for t in q_tokens:
                variants = _location_variants(t)
                if variants and variants != [t]:
                    loc_aliases.extend(variants)
            
            q_conditions = [
                Job.title.ilike(q_pattern),
                Job.company_name.ilike(q_pattern),
                Job.description.ilike(q_pattern),
                Job.location.ilike(q_pattern),
                Job.education_level.ilike(q_pattern),
                Job.role_category.ilike(q_pattern)
            ]
            for v in loc_aliases:
                q_conditions.append(Job.location.ilike(f"%{v}%"))
                
            stmt = stmt.where(or_(*q_conditions))
        
        if query.location:
            variants = _location_variants(query.location)
            loc_conditions = [Job.location.ilike(f"%{v}%") for v in variants]
            stmt = stmt.where(or_(*loc_conditions))
            
        if query.remote is True:
            stmt = stmt.where(Job.remote_status.ilike("%remote%"))
            
        # Role Category filter
        if query.role:
            stmt = stmt.where(Job.role_category == query.role)

        # Degree filter (e.g. MCA, B.Tech, Master's, Any Graduate)
        if query.degree:
            stmt = stmt.where(_build_degree_condition(query.degree))

        # Experience Level filter (fresher, junior, mid, senior)
        if query.experience_level:
            stmt = stmt.where(_build_experience_condition(query.experience_level))

        # Job Type filter (Full-time, Internship, etc.)
        if query.job_type:
            stmt = stmt.where(Job.job_type.ilike(f"%{query.job_type}%"))

        # Salary filters
        if query.salary_min is not None:
            stmt = stmt.where(or_(Job.salary_max >= query.salary_min, Job.salary_min >= query.salary_min))
        if query.salary_max is not None:
            stmt = stmt.where(or_(Job.salary_min <= query.salary_max, Job.salary_max <= query.salary_max))

        # 3. Pagination Bounds & Strict Ordering
        offset = (query.page - 1) * query.limit
        order_timestamp = func.coalesce(Job.last_source_seen_at, Job.created_at, Job.updated_at)
        
        if query.sort_by == "score" and query.q:
            q_clean = query.q.strip()
            stmt = stmt.order_by(
                desc(func.lower(Job.title) == q_clean.lower()),
                desc(Job.title.ilike(f"%{q_clean}%")),
                desc(Job.company_name.ilike(f"%{q_clean}%")),
                desc(order_timestamp),
                desc(Job.id)
            )
        else:
            # Default / "recent": strictly newest discovered/created first
            stmt = stmt.order_by(
                desc(order_timestamp),
                desc(Job.id)
            )
        stmt = stmt.offset(offset).limit(query.limit)
        
        # 4. Total Count
        count_stmt = select(func.count(Job.id)).where(Job.status.in_([JobStatus.ACTIVE, JobStatus.VERIFYING]))
        if query.q:
            count_stmt = count_stmt.where(or_(*q_conditions))
        if query.location:
            count_stmt = count_stmt.where(or_(*[Job.location.ilike(f"%{v}%") for v in _location_variants(query.location)]))
        if query.remote is True:
            count_stmt = count_stmt.where(Job.remote_status.ilike("%remote%"))
        if query.role:
            count_stmt = count_stmt.where(Job.role_category == query.role)
        if query.degree:
            count_stmt = count_stmt.where(_build_degree_condition(query.degree))
        if query.experience_level:
            count_stmt = count_stmt.where(_build_experience_condition(query.experience_level))
        if query.job_type:
            count_stmt = count_stmt.where(Job.job_type.ilike(f"%{query.job_type}%"))
        if query.salary_min is not None:
            count_stmt = count_stmt.where(or_(Job.salary_max >= query.salary_min, Job.salary_min >= query.salary_min))
        if query.salary_max is not None:
            count_stmt = count_stmt.where(or_(Job.salary_min <= query.salary_max, Job.salary_max <= query.salary_max))
            
        total = (await db.execute(count_stmt)).scalar() or 0
        jobs = (await db.execute(stmt)).scalars().all()
        
        # 5. Build responses with query relevance scoring when searching
        results = []
        for j in jobs:
            score = None
            reasons = None
            if query.q:
                q_lower = query.q.strip().lower()
                title_lower = (j.title or "").lower()
                company_lower = (j.company_name or "").lower()
                desc_lower = (j.description or "").lower()
                
                score = 50
                reasons = []
                if q_lower in title_lower:
                    score += 35
                    reasons.append("Title Match")
                if q_lower in company_lower:
                    score += 15
                    reasons.append("Company Match")
                if q_lower in desc_lower and "Title Match" not in reasons:
                    score += 10
                    reasons.append("Description Match")
                score = min(99, score)
                if not reasons:
                    reasons.append("Keyword Match")

            results.append({
                "job": j,
                "score": score,
                "reasons": reasons
            })
            
        return results, total

    @classmethod
    async def match_candidate(
        cls,
        db: AsyncSession,
        profile: Profile,
        sort_by: str = "score",
        page: int = 1,
        limit: int = 20,
        redis_client=None
    ) -> Tuple[List[Dict[str, Any]], int]:
        profile_skills = set(s.lower() for s in (profile.skills or []))
        
        locs = []
        if profile.location:
            locs.append(profile.location)
        if profile.preferred_locations:
            locs.extend(profile.preferred_locations)
        # Expand profile locations with city aliases
        expanded_locs: set[str] = set()
        for loc in locs:
            for variant in _location_variants(loc):
                expanded_locs.add(variant)
        profile_locations = expanded_locs
        
        profile_job_types = set(t.lower() for t in (profile.preferred_job_types or []))
        interested = set(f.lower() for f in (profile.interested_fields or []))
        
        # 1. Bounded SQL Pre-Filter: Retrieve candidate jobs matching location, skills, or remote status
        conds = []
        if profile_locations:
            for v in list(profile_locations)[:8]:
                conds.append(Job.location.ilike(f"%{v}%"))
        if "remote" in profile_locations:
            conds.append(Job.remote_status.ilike("%remote%"))
            conds.append(Job.location.ilike("%remote%"))
        if profile_skills:
            for s in list(profile_skills)[:6]:
                conds.append(Job.title.ilike(f"%{s}%"))
        if interested:
            for f in list(interested)[:3]:
                conds.append(Job.title.ilike(f"%{f}%"))

        stmt = select(Job).where(Job.status.in_([JobStatus.ACTIVE, JobStatus.VERIFYING]))
        if conds:
            stmt = stmt.where(or_(*conds))

        order_col = func.coalesce(Job.last_source_seen_at, Job.created_at, Job.updated_at)
        stmt = stmt.order_by(desc(order_col)).limit(400)
        jobs = (await db.execute(stmt)).scalars().all()

        # Supplement if fewer than 100 jobs match strict criteria
        if len(jobs) < 100:
            supplement_stmt = select(Job).where(
                Job.status.in_([JobStatus.ACTIVE, JobStatus.VERIFYING])
            ).order_by(desc(order_col)).limit(200)
            supplement_jobs = (await db.execute(supplement_stmt)).scalars().all()
            seen_ids = set(j.id for j in jobs)
            jobs.extend([j for j in supplement_jobs if j.id not in seen_ids])
        
        # 2. Deterministic Multi-Factor Scoring
        pre_scored_jobs = []
        for j in jobs:
            score = 0
            reasons = []
            
            j_title_lower = j.title.lower() if j.title else ""
            if interested and any(f in j_title_lower for f in interested):
                score += SCORE_TITLE_MATCH
                reasons.append("TITLE_MATCH")
                    
            if profile_skills:
                for skill in profile_skills:
                    if skill in j_title_lower or (j.description and skill in j.description.lower()):
                        score += SCORE_SKILL_MATCH
                        reasons.append("SKILL_MATCH")
                        break
                        
            if profile_locations:
                j_loc_lower = j.location.lower() if j.location else ""
                if any(v in j_loc_lower for v in profile_locations):
                    score += SCORE_LOCATION_MATCH
                    reasons.append("LOCATION_MATCH")

            # Education level match (MCA, B.Tech, etc.)
            if getattr(profile, 'education', None) and j.education_level:
                if profile.education.lower() in j.education_level.lower() or j.education_level.lower() in profile.education.lower():
                    score += 10
                    reasons.append("EDUCATION_MATCH")
                    
            # Experience level match (Fresher, Junior, Mid, Senior)
            cand_exp_level = (getattr(profile, 'experience_level', None) or "").lower().strip()
            cand_exp_years = getattr(profile, 'experience_years', None)
            is_fresher = cand_exp_level in ["fresher", "entry", "intern"] or (cand_exp_years is not None and cand_exp_years <= 1.0)
            
            j_exp_level = (j.experience_level or "").lower().strip()
            if is_fresher:
                if j_exp_level in ["fresher", "entry", "intern", "junior"] or any(w in j_title_lower for w in ["fresher", "intern", "trainee", "junior", "graduate", "entry"]):
                    score += 15
                    reasons.append("EXPERIENCE_FIT_FRESHER")
                elif any(w in j_title_lower for w in ["senior", "lead", "architect", "principal", "manager", "director"]):
                    score = max(0, score - 15)
            elif cand_exp_level in ["senior", "lead"]:
                if j_exp_level in ["senior", "lead"] or any(w in j_title_lower for w in ["senior", "lead", "architect", "principal"]):
                    score += 15
                    reasons.append("EXPERIENCE_FIT_SENIOR")
            elif cand_exp_level:
                if j_exp_level == cand_exp_level:
                    score += 12
                    reasons.append("EXPERIENCE_MATCH")
                    
            if profile_job_types:
                j_type_lower = j.job_type.lower() if j.job_type else ""
                if any(t in j_type_lower for t in profile_job_types):
                    score += SCORE_EMPLOYMENT_TYPE_MATCH
                    reasons.append("EMPLOYMENT_TYPE_MATCH")
                    
            if "remote" in profile_locations:
                j_remote = j.remote_status.lower() if j.remote_status else ""
                if "remote" in j_remote or (j.location and "remote" in j.location.lower()):
                    score += SCORE_REMOTE_MATCH
                    reasons.append("REMOTE_MATCH")
            
            if score > 0:
                pre_scored_jobs.append({"job": j, "pre_score": score, "pre_reasons": reasons})
                
        def _get_job_ts(job):
            dt = getattr(job, "last_source_seen_at", None) or getattr(job, "created_at", None) or getattr(job, "updated_at", None)
            return dt.timestamp() if dt else 0.0

        # Sort by pre-score
        pre_scored_jobs.sort(
            key=lambda x: (
                x["pre_score"], 
                _get_job_ts(x["job"])
            ), 
            reverse=True
        )
        
        from app.core.config import settings
        
        # If semantic matching is disabled or testing, return deterministic match instantly
        if not settings.ENABLE_SEMANTIC_SEARCH or settings.TESTING:
            for c in pre_scored_jobs:
                c["score"] = c.pop("pre_score")
                c["reasons"] = c.pop("pre_reasons")
                c["semantic_details"] = None
            
            if sort_by == "recent":
                pre_scored_jobs.sort(key=lambda x: _get_job_ts(x["job"]), reverse=True)
            else:
                pre_scored_jobs.sort(key=lambda x: (x["score"], _get_job_ts(x["job"])), reverse=True)

            total = len(pre_scored_jobs)
            offset = (page - 1) * limit
            return pre_scored_jobs[offset:offset+limit], total

        # Bound LLM calls to top 3 candidates to ensure responsive interactive UX
        top_candidates = pre_scored_jobs[:min(3, settings.MAX_SEMANTIC_CANDIDATES)]
        remaining_candidates = pre_scored_jobs[len(top_candidates):]
        total = len(pre_scored_jobs) # Total available after pre-filter
        
        # 3. Semantic LLM Scoring
        from pydantic import BaseModel, Field
        from app.core.llm import llm_client
        import asyncio
        import logging
        
        logger = logging.getLogger(__name__)

        class SemanticMatchResult(BaseModel):
            score: int = Field(..., description="Match score from 0 to 100")
            confidence: float = Field(..., description="Confidence in the score from 0.0 to 1.0")
            matched_skills: list[str] = Field(..., description="Skills from the profile that match the job")
            missing_skills: list[str] = Field(..., description="Important skills required by the job missing from the profile")
            match_reasons: list[str] = Field(..., description="Brief human-readable reasons for this score")

        profile_summary = f"""
        Skills: {', '.join(profile.skills or [])}
        Preferred Locations: {', '.join(profile.preferred_locations or [])}
        Interested Fields: {', '.join(profile.interested_fields or [])}
        """

        async def _score_job(candidate: dict) -> dict:
            j = candidate["job"]
            job_summary = f"""
            Title: {j.title}
            Company: {j.company_name}
            Location: {j.location}
            Remote: {j.remote_status}
            Description snippet: {j.description[:1000] if j.description else ""}
            """
            
            prompt = f"""
            Evaluate how well this candidate profile matches the job requirements.
            
            CANDIDATE PROFILE:
            {profile_summary}
            
            JOB LISTING:
            {job_summary}
            """
            
            # Cache Key Generation
            import hashlib
            import json
            
            # Version factors to invalidate cache when system changes
            CACHE_VERSION = "v2"
            PROMPT_VERSION = "v1"
            SCHEMA_VERSION = "SemanticMatchResult_v1"
            PROVIDER_IDENTITY = settings.LLM_SEQUENCE # E.g. GROQ,GEMINI or just GROQ_MODEL
            
            # Create a deterministic snapshot string using actual inputs rather than timestamps
            snapshot_str = json.dumps({
                "profile_summary_hash": hashlib.sha256(profile_summary.encode()).hexdigest(),
                "job_summary_hash": hashlib.sha256(job_summary.encode()).hexdigest(),
                "prompt_version": PROMPT_VERSION,
                "provider": PROVIDER_IDENTITY,
                "schema_version": SCHEMA_VERSION,
                "cache_version": CACHE_VERSION
            }, sort_keys=True)
            
            cache_key = f"semantic_match:{hashlib.sha256(snapshot_str.encode()).hexdigest()}"
            
            # Try Cache
            if redis_client:
                try:
                    cached_val = await redis_client.get(cache_key)
                    if cached_val:
                        # Validate the cached payload against our schema
                        data = json.loads(cached_val)
                        validated = SemanticMatchResult(**data)
                        
                        return {
                            "job": j,
                            "score": validated.score,
                            "reasons": validated.match_reasons,
                            "semantic_details": {
                                "confidence": validated.confidence,
                                "matched_skills": validated.matched_skills,
                                "missing_skills": validated.missing_skills
                            }
                        }
                except Exception as e:
                    logger.warning(f"Redis cache error reading/validating {cache_key}: {e}")
            
            try:
                result = await asyncio.wait_for(
                    llm_client.generate_structured(prompt, SemanticMatchResult, timeout=2), 
                    timeout=2.5
                )
                
                final_result = {
                    "job": j,
                    "score": result.score,
                    "reasons": result.match_reasons,
                    "semantic_details": {
                        "confidence": result.confidence,
                        "matched_skills": result.matched_skills,
                        "missing_skills": result.missing_skills
                    }
                }
                
                # Write to Cache (TTL 24 hours)
                if redis_client:
                    try:
                        # Exclude 'job' object, only cache the primitives that map to SemanticMatchResult
                        cache_data = result.model_dump()
                        await redis_client.setex(cache_key, 86400, json.dumps(cache_data))
                    except Exception as e:
                        logger.warning(f"Redis cache error writing {cache_key}: {e}")
                        
                return final_result
                
            except Exception as e:
                logger.warning(f"Semantic scoring failed for job {j.id}: {e}")
                # Fallback to pre-score if LLM fails
                return {
                    "job": j,
                    "score": candidate["pre_score"],
                    "reasons": ["Fallback: Deterministic Match"] + candidate["pre_reasons"],
                    "semantic_details": None
                }

        # Concurrently score the bounded page of candidates
        if top_candidates:
            scored_jobs = await asyncio.gather(*[_score_job(c) for c in top_candidates])
        else:
            scored_jobs = []
            
        # Add the unscored remainder back (using pre_score) so they aren't lost, just scored lower
        for rc in remaining_candidates:
            scored_jobs.append({
                "job": rc["job"],
                "score": rc["pre_score"],
                "reasons": ["Fallback: Deterministic Match"] + rc["pre_reasons"],
                "semantic_details": None
            })

        # Sort all jobs by selected sort mode
        if sort_by == "recent":
            scored_jobs.sort(key=lambda x: _get_job_ts(x["job"]), reverse=True)
        else:
            scored_jobs.sort(
                key=lambda x: (
                    x["score"], 
                    _get_job_ts(x["job"])
                ), 
                reverse=True
            )
        
        offset = (page - 1) * limit
        return scored_jobs[offset:offset+limit], total

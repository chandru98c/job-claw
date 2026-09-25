import re
from typing import List, Tuple, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, desc, asc, func
from app.database.models import Job, JobStatus, Profile
from app.schemas.search import SearchQuery

# Strict deterministic scoring model
SCORE_TITLE_MATCH = 40
SCORE_SKILL_MATCH = 30
SCORE_LOCATION_MATCH = 15
SCORE_REMOTE_MATCH = 10
SCORE_EMPLOYMENT_TYPE_MATCH = 5

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
            q_pattern = f"%{query.q}%"
            stmt = stmt.where(
                or_(
                    Job.title.ilike(q_pattern),
                    Job.company_name.ilike(q_pattern)
                )
            )
        
        if query.location:
            loc_pattern = f"%{query.location}%"
            stmt = stmt.where(Job.location.ilike(loc_pattern))
            
        if query.remote is True:
            stmt = stmt.where(Job.remote_status.ilike("%remote%"))
            
        # 3. Pagination Bounds
        offset = (query.page - 1) * query.limit
        stmt = stmt.order_by(desc(Job.updated_at), asc(Job.id))
        stmt = stmt.offset(offset).limit(query.limit)
        
        # 4. Total Count
        count_stmt = select(func.count(Job.id)).where(Job.status.in_([JobStatus.ACTIVE, JobStatus.VERIFYING]))
        if query.q:
            count_stmt = count_stmt.where(or_(Job.title.ilike(q_pattern), Job.company_name.ilike(q_pattern)))
        if query.location:
            count_stmt = count_stmt.where(Job.location.ilike(loc_pattern))
        if query.remote is True:
            count_stmt = count_stmt.where(Job.remote_status.ilike("%remote%"))
            
        total = (await db.execute(count_stmt)).scalar()
        jobs = (await db.execute(stmt)).scalars().all()
        
        # 5. Build responses without fake matching scores. Open search just retrieves.
        results = []
        for j in jobs:
            results.append({
                "job": j,
                "score": None,
                "reasons": None
            })
            
        return results, total

    @classmethod
    async def match_candidate(
        cls,
        db: AsyncSession,
        profile: Profile,
        page: int = 1,
        limit: int = 20,
        redis_client=None
    ) -> Tuple[List[Dict[str, Any]], int]:
        
        # 1. Fetch active jobs
        stmt = select(Job).where(Job.status.in_([JobStatus.ACTIVE, JobStatus.VERIFYING]))
        jobs = (await db.execute(stmt)).scalars().all()
        
        profile_skills = set(s.lower() for s in (profile.skills or []))
        
        locs = []
        if profile.location:
            locs.append(profile.location)
        if profile.preferred_locations:
            locs.extend(profile.preferred_locations)
        profile_locations = set(l.lower() for l in locs)
        
        profile_job_types = set(t.lower() for t in (profile.preferred_job_types or []))
        interested = set(f.lower() for f in (profile.interested_fields or []))
        
        # 2. Cheap Deterministic Pre-Filter
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
                    if re.search(rf'\b{re.escape(skill)}\b', (j.title or "") + " " + (j.description or ""), re.IGNORECASE):
                        score += SCORE_SKILL_MATCH
                        reasons.append("SKILL_MATCH")
                        break
                        
            if profile_locations:
                j_loc_lower = j.location.lower() if j.location else ""
                if any(l in j_loc_lower for l in profile_locations):
                    score += SCORE_LOCATION_MATCH
                    reasons.append("LOCATION_MATCH")
                    
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
            
        # Keep loosely relevant jobs
            if score > 0:
                pre_scored_jobs.append({"job": j, "pre_score": score, "pre_reasons": reasons})
                
        # Sort by pre-score and take top candidates for semantic analysis
        pre_scored_jobs.sort(
            key=lambda x: (
                x["pre_score"], 
                x["job"].updated_at.timestamp() if x["job"].updated_at else 0
            ), 
            reverse=True
        )
        
        from app.core.config import settings
        
        # If semantic matching is disabled (or we are in tests that shouldn't hit it), skip LLM entirely
        if not settings.ENABLE_SEMANTIC_SEARCH or settings.TESTING:
            for c in pre_scored_jobs:
                c["score"] = c.pop("pre_score")
                c["reasons"] = c.pop("pre_reasons")
                c["semantic_details"] = None
            
            total = len(pre_scored_jobs)
            offset = (page - 1) * limit
            return pre_scored_jobs[offset:offset+limit], total

        # Bound LLM calls to max semantic candidates (e.g. 20)
        # We only semantically score the absolute top N matches to save cost.
        top_candidates = pre_scored_jobs[:settings.MAX_SEMANTIC_CANDIDATES]
        remaining_candidates = pre_scored_jobs[settings.MAX_SEMANTIC_CANDIDATES:]
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
                result = await llm_client.generate_structured(prompt, SemanticMatchResult, timeout=30)
                
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

        # Sort all jobs by their final score
        scored_jobs.sort(
            key=lambda x: (
                x["score"], 
                x["job"].updated_at.timestamp() if x["job"].updated_at else 0
            ), 
            reverse=True
        )
        
        offset = (page - 1) * limit
        return scored_jobs[offset:offset+limit], total

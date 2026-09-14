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
        limit: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        
        # Resume matching acts on ALL valid jobs, scoring them deterministically
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
        
        scored_jobs = []
        for j in jobs:
            score = 0
            reasons = []
            
            j_title_lower = j.title.lower() if j.title else ""
            j_desc_tokens = cls._tokenize(j.description)
            j_title_tokens = cls._tokenize(j.title)
            
            # TITLE MATCH (We don't have explicit profile titles, so we match skills against title or maybe they put roles in skills)
            # Actually, UserProfile has `interested_fields`. Let's use that for Title Match.
            interested = set(f.lower() for f in (profile.interested_fields or []))
            if interested:
                if any(f in j_title_lower for f in interested):
                    score += SCORE_TITLE_MATCH
                    reasons.append("TITLE_MATCH")
                    
            # SKILL MATCH (Avoid substring false positives by using word boundaries/tokens)
            if profile_skills:
                # Check if any skill exactly matches a token in title or description
                matched_skill = False
                for skill in profile_skills:
                    # Multi-word skills might not match simple token sets perfectly if tokenized strictly by \w+.
                    # But if we regex search word boundaries in original text:
                    if re.search(rf'\b{re.escape(skill)}\b', (j.title or "") + " " + (j.description or ""), re.IGNORECASE):
                        matched_skill = True
                        break
                if matched_skill:
                    score += SCORE_SKILL_MATCH
                    reasons.append("SKILL_MATCH")
                    
            # LOCATION MATCH
            if profile_locations:
                j_loc_lower = j.location.lower() if j.location else ""
                if any(l in j_loc_lower for l in profile_locations):
                    score += SCORE_LOCATION_MATCH
                    reasons.append("LOCATION_MATCH")
                    
            # EMPLOYMENT TYPE MATCH
            if profile_job_types:
                j_type_lower = j.job_type.lower() if j.job_type else ""
                if any(t in j_type_lower for t in profile_job_types):
                    score += SCORE_EMPLOYMENT_TYPE_MATCH
                    reasons.append("EMPLOYMENT_TYPE_MATCH")
                    
            # REMOTE MATCH
            if "remote" in profile_locations:
                j_remote = j.remote_status.lower() if j.remote_status else ""
                if "remote" in j_remote or "remote" in j_loc_lower:
                    # Prevent double scoring if already got location match for remote
                    if "REMOTE_MATCH" not in reasons:
                        score += SCORE_REMOTE_MATCH
                        reasons.append("REMOTE_MATCH")
            
            # Only include if score > 0
            if score > 0:
                scored_jobs.append({
                    "job": j,
                    "score": score,
                    "reasons": reasons
                })
                
        # Deterministic Sort: score DESC, updated_at DESC, id ASC
        scored_jobs.sort(
            key=lambda x: (
                x["score"], 
                x["job"].updated_at.timestamp() if x["job"].updated_at else 0, 
                x["job"].id
            ), 
            reverse=True
        )
        
        # Paginate
        total = len(scored_jobs)
        offset = (page - 1) * limit
        paginated = scored_jobs[offset:offset+limit]
        
        return paginated, total

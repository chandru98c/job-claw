import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.database import AsyncSessionLocal
from app.database.models import (
    SavedSearch, Profile, Source, JobRecommendation, RecommendationState,
    Task, TaskEvent, TaskStatus, TaskEventType
)
from app.discovery.registry import StrategyRegistry
from app.discovery.engine import DiscoveryEngine
from app.discovery.budget import ResourceBudget
from app.core.http import DomainPolicy
from app.canonicalization.pipeline import process_raw_job
from app.schemas.discovery import RawJob
from app.schemas.search import SearchQuery
from app.services.search import SearchService

# Assuming we build a similar registry to what's in discovery.py
from app.workers.discovery import build_registry
from app.workers.tasks import log_event

logger = logging.getLogger(__name__)

async def execute_saved_search_task(ctx: Dict[Any, Any], search_id: str) -> str:
    """
    Executes a saved search.
    1. Acquires a lock (using Redis or DB).
    2. Runs DiscoveryEngine on active sources.
    3. Canonicalizes results.
    4. Runs Matching engine.
    5. Upserts JobRecommendations.
    """
    redis = ctx.get("redis")
    if not redis:
        return "Failed: No redis connection"
        
    lock_key = f"lock:saved_search:{search_id}"
    lock = redis.lock(lock_key, timeout=3600) # 1 hour max run
    
    acquired = await lock.acquire(blocking=False)
    if not acquired:
        logger.warning(f"Saved search {search_id} is already running.")
        return "Skipped: Already running"
        
    try:
        async with AsyncSessionLocal() as session:
            # Check worker mode
            mode_bytes = await redis.get("worker:mode")
            if mode_bytes and mode_bytes.decode("utf-8") == "server":
                logger.info("Worker is in SERVER mode. Skipping saved search.")
                return "Skipped: Worker in SERVER mode"
                
            # Load Search
            result = await session.execute(
                select(SavedSearch).options(selectinload(SavedSearch.profile)).where(SavedSearch.id == search_id)
            )
            saved_search = result.scalar_one_or_none()
            
            if not saved_search or not saved_search.enabled:
                return "Skipped: Not found or disabled"
                
            profile = saved_search.profile
            if not profile:
                return "Failed: No profile"
                
            # Snapshot
            query_snapshot = SearchQuery(
                q=saved_search.query,
                location=saved_search.location,
                remote=saved_search.remote,
                page=1,
                limit=100  # Bounded recommendations per run
            )
            
            # Fetch active sources to scan (bounded to first 5 for limits)
            sources_res = await session.execute(select(Source).where(Source.is_active == True).limit(5))
            active_sources = sources_res.scalars().all()
            
            # Initialize Pipeline
            registry = build_registry()
            budget = ResourceBudget(max_requests=50, max_duration_seconds=300)
            engine = DiscoveryEngine(registry=registry, budget=budget)
            
            total_raw_jobs = []
            
            for source in active_sources:
                if not source.start_url:
                    continue
                try:
                    disc_res = await engine.discover(source.start_url)
                    if disc_res.raw_jobs:
                        total_raw_jobs.extend(disc_res.raw_jobs)
                except Exception as e:
                    logger.error(f"Error discovering {source.start_url}: {e}")
                    
            # Canonicalize (must be synchronous for DB logic in process_raw_job)
            # Wait, process_raw_job is a synchronous function that takes a synchronous Session.
            # We can use run_in_executor, or we can use an AsyncSession variant if it exists.
            # But process_raw_job takes `SessionLocal()` - wait, the canonicalization worker creates its own sync session.
            # So we will do that.
            from app.database.database import SessionLocal
            
            canonical_job_ids = set()
            sync_db = SessionLocal()
            try:
                for r_job in total_raw_jobs:
                    try:
                        res, c_job = process_raw_job(sync_db, r_job)
                        if c_job:
                            canonical_job_ids.add(c_job.id)
                    except Exception as e:
                        logger.error(f"Error canonicalizing {r_job.absolute_url}: {e}")
                sync_db.commit()
            finally:
                sync_db.close()
                
            if not canonical_job_ids:
                saved_search.last_run_at = datetime.now(timezone.utc)
                await session.commit()
                return "Completed: No jobs discovered"
                
            # Matching
            # The SearchService can filter by query/location
            # Let's run `SearchService.open_search` with the snapshot
            matches, total = await SearchService.open_search(session, query_snapshot)
            
            # Filter matches to only the ones we just discovered/canonicalized? 
            # Actually, the saved search should surface ANY jobs in the DB matching the criteria,
            # but usually it's run periodically. Let's process the top results from `open_search`.
            
            recommendations_created = 0
            for item in matches:
                job = item["job"]
                score = item["score"] or 0
                reasons = item["reasons"] or []
                
                # Deduplication
                rec_res = await session.execute(
                    select(JobRecommendation)
                    .where(JobRecommendation.profile_id == profile.id, JobRecommendation.job_id == job.id)
                )
                existing_rec = rec_res.scalar_one_or_none()
                
                if existing_rec:
                    existing_rec.score = score
                    existing_rec.reasons = reasons
                    # Reopening logic
                    if existing_rec.state == RecommendationState.EXPIRED and job.status.value == "ACTIVE":
                        existing_rec.state = RecommendationState.NEW
                        existing_rec.surfaced_at = None
                else:
                    new_rec = JobRecommendation(
                        profile_id=profile.id,
                        job_id=job.id,
                        score=score,
                        reasons=reasons,
                        state=RecommendationState.NEW
                    )
                    session.add(new_rec)
                    recommendations_created += 1
                    
            saved_search.last_run_at = datetime.now(timezone.utc)
            await session.commit()
            
            return f"Completed: Discovered {len(total_raw_jobs)}, Canonicalized {len(canonical_job_ids)}, Recommendations created: {recommendations_created}"

    except Exception as e:
        logger.error(f"Saved search task failed: {e}")
        raise e
    finally:
        await lock.release()

async def scheduled_saved_searches(ctx: Dict[Any, Any]):
    """
    CRON task to trigger enabled saved searches.
    """
    redis = ctx.get("redis")
    if not redis:
        return
        
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(SavedSearch).where(SavedSearch.enabled == True))
        searches = res.scalars().all()
        
        for search in searches:
            await redis.enqueue_job("execute_saved_search_task", search.id)

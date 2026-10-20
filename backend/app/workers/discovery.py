"""
ARQ discovery task: runs the Discovery Engine inside the worker infrastructure.

Flow:
  POST /tasks → PostgreSQL → Redis → ARQ → discovery_task → DiscoveryEngine → RawJobs

Emits structured TaskEvents throughout execution.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select

from app.database.database import AsyncSessionLocal
from app.database.models import Task, TaskEvent, TaskStatus, TaskEventType, Source, CircuitStatus
from app.workers.tasks import log_event
from app.discovery.registry import StrategyRegistry
from app.discovery.engine import DiscoveryEngine
from app.discovery.budget import ResourceBudget
from app.core.http import DomainPolicy

# Import strategies for registration
from app.discovery.adapters.greenhouse import GreenhouseAdapter
from app.discovery.adapters.lever import LeverAdapter
from app.discovery.adapters.ashby import AshbyAdapter
from app.discovery.adapters.workable import WorkableAdapter
from app.discovery.adapters.smartrecruiters import SmartRecruitersAdapter
from app.discovery.adapters.workday import WorkdayAdapter
from app.discovery.adapters.zohorecruit import ZohoRecruitAdapter
from app.discovery.adapters.naukri import NaukriAdapter
from app.discovery.adapters.recruitee import RecruiteeAdapter
from app.discovery.adapters.breezy import BreezyAdapter
from app.discovery.adapters.teamtailor import TeamtailorAdapter
from app.discovery.adapters.personio import PersonioAdapter
from app.discovery.adapters.bamboohr import BambooHRAdapter
from app.discovery.adapters.keka import KekaAdapter
from app.discovery.adapters.darwinbox import DarwinboxAdapter
from app.discovery.adapters.wordpress import WordPressAdapter
from app.discovery.strategies.career_page import CareerPageStrategy
from app.discovery.strategies.robots import RobotsStrategy
from app.discovery.strategies.sitemap import SitemapStrategy
from app.discovery.strategies.llm import LLMStrategy

logger = logging.getLogger(__name__)


def build_registry() -> StrategyRegistry:
    """Build and populate the strategy registry at task startup."""
    registry = StrategyRegistry()
    # Direct ATS adapters (priority 10-15)
    registry.register(GreenhouseAdapter())
    registry.register(LeverAdapter())
    registry.register(AshbyAdapter())
    registry.register(WorkableAdapter())
    registry.register(SmartRecruitersAdapter())
    registry.register(WorkdayAdapter())       # HCL, Cognizant, Capgemini, Accenture India
    registry.register(ZohoRecruitAdapter())   # Zoho, Agnikul, Chennai/South India tech startups
    registry.register(NaukriAdapter())        # Naukri India tech search aggregator
    registry.register(RecruiteeAdapter())     # Recruitee public JSON offers API
    registry.register(BreezyAdapter())        # Breezy HR public JSON endpoint
    registry.register(TeamtailorAdapter())    # Teamtailor public RSS/XML feed
    registry.register(PersonioAdapter())      # Personio public search.json API
    registry.register(BambooHRAdapter())      # BambooHR public embed2 JSON API
    registry.register(KekaAdapter())          # Keka public embed API (India tech startups & SMEs)
    registry.register(DarwinboxAdapter())     # Darwinbox public candidate API (India enterprises)
    registry.register(WordPressAdapter())     # WordPress REST API (/wp-json/wp/v2/posts and job-listings)
    # Heuristic strategies
    registry.register(CareerPageStrategy())
    registry.register(RobotsStrategy())
    registry.register(SitemapStrategy())
    # Last-resort fallback
    registry.register(LLMStrategy())
    return registry


async def discovery_task(ctx, task_id: str, input_url: str):
    """
    ARQ worker task for running job discovery.
    """
    logger.info(f"Starting discovery_task for task_id={task_id}, url={input_url}")

    # ─── Task State: RUNNING ────────────────────────────────────────
    async with AsyncSessionLocal() as session:
        from sqlalchemy import text
        from app.database.models import CircuitStatus
        
        # --- Circuit Breaker: Check & Claim ---
        task = await session.get(Task, task_id)
        if not task:
            logger.warning(f"Task {task_id} not found in database. Discarding stale queue job.")
            return "Skipped: Task not found in database"
            
        source_id = task.target_id
        source = await session.get(Source, source_id) if source_id else None
        
        if source:
            if not source.is_active:
                return "Skipped: Source is disabled"
                
            if source.circuit_status == CircuitStatus.OPEN:
                now_utc = datetime.now(timezone.utc)
                if source.next_retry_at and now_utc < source.next_retry_at:
                    logger.info(f"Source {source_id} is OPEN and in cooldown until {source.next_retry_at}. Skipping.")
                    return "Skipped: Circuit OPEN"
                
                # Cooldown expired, atomic claim for HALF_OPEN
                stmt = text("""
                    UPDATE sources 
                    SET circuit_status = 'HALF_OPEN' 
                    WHERE id = :id 
                      AND circuit_status = 'OPEN' 
                      AND (next_retry_at IS NULL OR next_retry_at <= :now)
                    RETURNING id
                """)
                result = await session.execute(stmt, {"id": source_id, "now": now_utc})
                if not result.scalar():
                    logger.info(f"Source {source_id} HALF_OPEN claim failed (another worker won). Skipping.")
                    return "Skipped: Lost HALF_OPEN claim"
                
                # We won the claim, source is now HALF_OPEN in this transaction

        if task.status in (TaskStatus.SUCCEEDED, TaskStatus.CANCELLED, TaskStatus.FAILED):
            return "Skipped: Already finished"

        task.status = TaskStatus.RUNNING
        if not task.started_at:
            task.started_at = datetime.now(timezone.utc)
        if ctx.get('job_try', 1) > 1:
            task.retry_count = ctx.get('job_try') - 1
            await log_event(session, task_id, TaskEventType.RETRY, {"attempt": ctx.get('job_try')})
        await session.commit()
        await log_event(session, task_id, TaskEventType.STARTED, {"url": input_url})

    # ─── Event Callback ─────────────────────────────────────────────
    async def emit_event(event_type: str, payload: dict):
        try:
            async with AsyncSessionLocal() as session:
                await log_event(session, task_id, TaskEventType.PROGRESS, {
                    "discovery_event": event_type,
                    **payload,
                })
        except Exception as e:
            logger.warning(f"Failed to emit event: {e}")

    # ─── Run Discovery Engine ───────────────────────────────────────
    try:
        registry = build_registry()
        budget = ResourceBudget()
        engine = DiscoveryEngine(
            registry=registry,
            budget=budget,
            event_callback=emit_event,
        )

        from app.schemas.discovery import SourceConfig
        source_config = None
        async with AsyncSessionLocal() as session:
            task = await session.get(Task, task_id)
            if task and task.target_id:
                s = await session.get(Source, task.target_id)
                if s:
                    source_config = SourceConfig(
                        source_id=s.id,
                        company=s.domain,
                        domain=s.domain,
                        careers_url=s.start_url,
                        ats_type=s.ats_type,
                        enabled=s.is_active
                    )

        discovery_result = await engine.discover(input_url, source_config=source_config)

        # ─── Task State: SUCCEEDED ──────────────────────────────────
        async with AsyncSessionLocal() as session:
            task = await session.get(Task, task_id)
            
            # --- Handle Engine Soft Failure (Adapter errors) ---
            if not discovery_result.success and discovery_result.errors:
                first_error = discovery_result.errors[0]
                error_msg = first_error.message
                
                if task and task.status not in (TaskStatus.CANCELLED, TaskStatus.SUCCEEDED, TaskStatus.FAILED):
                    task.status = TaskStatus.FAILED
                    task.finished_at = datetime.now(timezone.utc)
                    task.error = error_msg
                    await session.commit()
                    await log_event(session, task_id, TaskEventType.ERROR, {"error": error_msg})
                    
                if task and task.target_id:
                    source = await session.get(Source, task.target_id)
                    if source:
                        from app.discovery.health import calculate_backoff, classify_error, CIRCUIT_FAILURE_THRESHOLD
                        source.last_attempt_at = datetime.now(timezone.utc)
                        is_quota_error = any(kw in error_msg.lower() for kw in ("rate limit", "429", "quota", "resource_exhausted"))
                        if not is_quota_error:
                            source.last_failure_at = datetime.now(timezone.utc)
                            source.consecutive_failures = (source.consecutive_failures or 0) + 1
                            source.last_error = error_msg
                            
                            if source.consecutive_failures >= CIRCUIT_FAILURE_THRESHOLD or source.circuit_status == CircuitStatus.HALF_OPEN:
                                source.circuit_status = CircuitStatus.OPEN
                                delay = calculate_backoff(source.consecutive_failures, None)
                                source.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                        else:
                            source.last_error = "LLM extraction paused: transient rate limit / quota exhaustion"
                            
                        await session.commit()
                        
                return f"Failed with {len(discovery_result.errors)} errors"
            
            # --- Task State: SUCCEEDED ---
            if task and task.status not in (TaskStatus.CANCELLED, TaskStatus.SUCCEEDED, TaskStatus.FAILED):
                task.status = TaskStatus.SUCCEEDED
                task.finished_at = datetime.now(timezone.utc)
                task.metrics = {
                    "jobs_discovered": len(discovery_result.raw_jobs),
                    "accounting": discovery_result.accounting,
                }
                
                if discovery_result.raw_jobs:
                    from app.database.database import SessionLocal
                    from app.canonicalization.pipeline import process_raw_job
                    sync_db = SessionLocal()
                    try:
                        for r_job in discovery_result.raw_jobs:
                            try:
                                process_raw_job(sync_db, r_job)
                            except Exception as e:
                                logger.error(f"Error canonicalizing {r_job.title}: {e}")
                        sync_db.commit()
                    finally:
                        sync_db.close()
                
                await session.commit()
                await log_event(session, task_id, TaskEventType.COMPLETED, {
                    "jobs_discovered": len(discovery_result.raw_jobs),
                })
                
                # --- Circuit Breaker: Success ---
                if task.target_id:
                    source = await session.get(Source, task.target_id)
                    if source:
                        source.circuit_status = CircuitStatus.CLOSED
                        source.consecutive_failures = 0
                        source.last_success_at = datetime.now(timezone.utc)
                        source.last_attempt_at = datetime.now(timezone.utc)
                        source.next_retry_at = None
                        source.last_error = None
                        await session.commit()

        return f"Discovered {len(discovery_result.raw_jobs)} jobs"

    except asyncio.CancelledError:
        logger.warning(f"Discovery task {task_id} cancelled.")
        async with AsyncSessionLocal() as session:
            task = await session.get(Task, task_id)
            if task and task.status not in (TaskStatus.SUCCEEDED, TaskStatus.FAILED):
                task.status = TaskStatus.CANCELLED
                task.finished_at = datetime.now(timezone.utc)
                await session.commit()
                await log_event(session, task_id, TaskEventType.CANCELLED)
        raise

    except Exception as e:
        logger.error(f"Discovery task {task_id} failed: {e}")
        async with AsyncSessionLocal() as session:
            task = await session.get(Task, task_id)
            if task and task.status not in (TaskStatus.CANCELLED, TaskStatus.SUCCEEDED, TaskStatus.FAILED):
                from app.core.config import settings
                if ctx.get('job_try', 1) < settings.WORKER_MAX_TRIES:
                    task.status = TaskStatus.RETRYING
                else:
                    task.status = TaskStatus.FAILED
                    task.finished_at = datetime.now(timezone.utc)
                task.error = str(e)
                await session.commit()
                event_type = TaskEventType.WARNING if task.status == TaskStatus.RETRYING else TaskEventType.ERROR
                await log_event(session, task_id, event_type, {"error": str(e)})
                
                # --- Circuit Breaker: Failure ---
                if task.target_id:
                    source = await session.get(Source, task.target_id)
                    if source:
                        from app.discovery.health import calculate_backoff, classify_error, CIRCUIT_FAILURE_THRESHOLD
                        
                        source.last_attempt_at = datetime.now(timezone.utc)
                        source.last_failure_at = datetime.now(timezone.utc)
                        source.consecutive_failures += 1
                        source.last_error = str(e)
                        
                        # We don't have HTTP status here usually since it's a raw exception, but we can try to extract it
                        status_code = None
                        if hasattr(e, "response") and hasattr(e.response, "status_code"):
                            status_code = e.response.status_code
                        
                        classification = classify_error(status_code, str(e))
                        # We might extract retry_after if available
                        retry_after = None
                        if hasattr(e, "response") and hasattr(e.response, "headers"):
                            ra_header = e.response.headers.get("Retry-After")
                            if ra_header and ra_header.isdigit():
                                retry_after = int(ra_header)
                                
                        if source.consecutive_failures >= CIRCUIT_FAILURE_THRESHOLD or source.circuit_status == CircuitStatus.HALF_OPEN:
                            source.circuit_status = CircuitStatus.OPEN
                            delay = calculate_backoff(source.consecutive_failures, retry_after)
                            source.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                            
                        await session.commit()

        raise

async def is_source_eligible_for_discovery(session, source: Source) -> bool:
    """Check if a source is eligible to be enqueued for discovery."""
    if not source.is_active:
        return False

    # Check circuit breaker
    if source.circuit_status == CircuitStatus.OPEN:
        if source.next_retry_at and datetime.now(timezone.utc) < source.next_retry_at:
            return False
        else:
            # Time to retry -> HALF_OPEN
            source.circuit_status = CircuitStatus.HALF_OPEN
            await session.commit()

    raw_start_url = getattr(source, "start_url", None)
    raw_domain = getattr(source, "domain", None)
    start_url = raw_start_url if isinstance(raw_start_url, str) and raw_start_url.strip() else None
    domain = raw_domain if isinstance(raw_domain, str) and raw_domain.strip() else None

    input_url = start_url if start_url is not None else (f"https://{domain}" if domain is not None else None)
    if input_url is None:
        return False

    # Deduplication: already queued or running
    existing_task = (
        await session.execute(
            select(Task).where(
                Task.target_id == source.id,
                Task.worker_type == "discovery_task",
                Task.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING]),
            )
        )
    ).scalar_one_or_none()

    if existing_task:
        return False
        
    return True

async def scheduled_registry_discovery(ctx):
    """Cron-triggered registry discovery (e.g. daily/weekly full sweeps)."""
    redis = ctx["redis"]

    # Check Worker Mode
    mode_bytes = await redis.get("worker:mode")
    if not mode_bytes or mode_bytes.decode("utf-8") != "server":
        return

    async with AsyncSessionLocal() as session:
        # Fetch active sources
        res = await session.execute(select(Source).where(Source.is_active == True))
        active_sources = res.scalars().all()

        queued_count = 0
        skipped_count = 0

        for source in active_sources:
            if not await is_source_eligible_for_discovery(session, source):
                skipped_count += 1
                continue
                
            raw_start_url = getattr(source, "start_url", None)
            raw_domain = getattr(source, "domain", None)
            start_url = raw_start_url if isinstance(raw_start_url, str) and raw_start_url.strip() else None
            domain = raw_domain if isinstance(raw_domain, str) and raw_domain.strip() else None
            input_url = start_url if start_url is not None else (f"https://{domain}" if domain is not None else None)


            # Enqueue
            task_id = str(uuid.uuid4())
            task = Task(
                id=task_id,
                target_id=source.id,
                worker_type="discovery_task",
                status=TaskStatus.QUEUED,
                created_at=datetime.now(timezone.utc),
            )
            session.add(task)
            session.add(
                TaskEvent(
                    task_id=task_id,
                    event_type=TaskEventType.QUEUED,
                    payload={"target_id": input_url, "source_id": source.id, "domain": domain},
                )
            )
            await session.flush()

            enqueued = await redis.enqueue_job("discovery_task", task_id, input_url, _job_id=task_id)
            if enqueued:
                queued_count += 1
            else:
                skipped_count += 1

        await session.commit()
        logger.info(f"Scheduled registry discovery: queued {queued_count}, skipped {skipped_count}.")


async def scheduled_working_sources_discovery(ctx):
    """
    Continuous Server-Mode Discovery:
    In SERVER mode, automatically and continuously sweeps verified working sources 
    (sources with proven jobs or active 0-failure boards) to capture newly posted jobs.
    Runs every 15 minutes.
    """
    redis = ctx.get("redis")
    if not redis:
        return

    # Check Worker Mode
    mode_bytes = await redis.get("worker:mode")
    if not mode_bytes or mode_bytes.decode("utf-8") != "server":
        return

    from app.database.models import JobSourceProvenance
    from sqlalchemy import or_, func

    async with AsyncSessionLocal() as session:
        # Prioritize sources with verified canonical jobs first, then healthy active sources
        proven_subq = select(func.distinct(JobSourceProvenance.source_id)).scalar_subquery()
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)

        stmt = (
            select(Source)
            .where(
                Source.is_active == True,
                Source.circuit_status != CircuitStatus.OPEN,
                or_(
                    Source.id.in_(proven_subq),
                    Source.consecutive_failures == 0
                ),
                or_(
                    Source.last_run_at.is_(None),
                    Source.last_run_at <= cutoff
                )
            )
            .order_by(Source.last_run_at.asc().nullsfirst())
            .limit(100) # Process in responsive batches of 100
        )
        working_sources = (await session.execute(stmt)).scalars().all()

        queued_count = 0
        skipped_count = 0

        for source in working_sources:
            if not await is_source_eligible_for_discovery(session, source):
                skipped_count += 1
                continue

            raw_start_url = getattr(source, "start_url", None)
            raw_domain = getattr(source, "domain", None)
            start_url = raw_start_url if isinstance(raw_start_url, str) and raw_start_url.strip() else None
            domain = raw_domain if isinstance(raw_domain, str) and raw_domain.strip() else None
            input_url = start_url if start_url is not None else (f"https://{domain}" if domain is not None else None)

            task_id = str(uuid.uuid4())
            task = Task(
                id=task_id,
                target_id=source.id,
                worker_type="discovery_task",
                status=TaskStatus.QUEUED,
                created_at=datetime.now(timezone.utc),
            )
            session.add(task)
            session.add(
                TaskEvent(
                    task_id=task_id,
                    event_type=TaskEventType.QUEUED,
                    payload={"target_id": input_url, "source_id": source.id, "domain": domain, "mode": "server_working_scan"},
                )
            )
            await session.flush()

            enqueued = await redis.enqueue_job("discovery_task", task_id, input_url, _job_id=task_id)
            if enqueued:
                queued_count += 1
            else:
                skipped_count += 1

        await session.commit()
        if queued_count > 0:
            logger.info(f"[Server Mode] Continuous working sources scan: queued {queued_count} boards ({skipped_count} skipped).")


async def scheduled_pending_sources_discovery(ctx):
    """
    Continuous Server-Mode Pending Sweep:
    In SERVER mode, sweeps batches of pending sources (consecutive_failures == 0,
    last_error is None, last_success_at is None), prioritizing direct ATS platforms.
    Runs periodically to continuously chew through pending boards and transition
    them to Working or Failing.
    """
    redis = ctx.get("redis")
    if not redis:
        return

    mode_bytes = await redis.get("worker:mode")
    if not mode_bytes or mode_bytes.decode("utf-8") != "server":
        return

    from app.database.models import JobSourceProvenance
    from sqlalchemy import or_, func, case, desc

    async with AsyncSessionLocal() as session:
        pend_cond = or_(Source.consecutive_failures == 0, Source.consecutive_failures.is_(None))
        
        known_ats_priority = case(
            (Source.ats_type.isnot(None) & (Source.ats_type != '') & (Source.ats_type != 'custom'), 1),
            else_=0
        )
        
        stmt = (
            select(Source)
            .where(
                Source.is_active == True,
                Source.circuit_status != CircuitStatus.OPEN,
                pend_cond,
                Source.last_error.is_(None),
                Source.last_success_at.is_(None)
            )
            .order_by(
                desc(known_ats_priority),
                Source.last_run_at.asc().nullsfirst(),
                Source.domain.asc()
            )
            .limit(200)
        )
        pending_sources = (await session.execute(stmt)).scalars().all()

        queued_count = 0
        skipped_count = 0

        for source in pending_sources:
            if not await is_source_eligible_for_discovery(session, source):
                skipped_count += 1
                continue

            raw_start_url = getattr(source, "start_url", None)
            raw_domain = getattr(source, "domain", None)
            start_url = raw_start_url if isinstance(raw_start_url, str) and raw_start_url.strip() else None
            domain = raw_domain if isinstance(raw_domain, str) and raw_domain.strip() else None
            input_url = start_url if start_url is not None else (f"https://{domain}" if domain is not None else None)

            task_id = str(uuid.uuid4())
            task = Task(
                id=task_id,
                target_id=source.id,
                worker_type="discovery_task",
                status=TaskStatus.QUEUED,
                created_at=datetime.now(timezone.utc),
            )
            session.add(task)
            session.add(
                TaskEvent(
                    task_id=task_id,
                    event_type=TaskEventType.QUEUED,
                    payload={"target_id": input_url, "source_id": source.id, "domain": domain, "mode": "scheduled_pending_sweep"},
                )
            )
            source.last_run_at = datetime.now(timezone.utc)
            await session.flush()

            enqueued = await redis.enqueue_job("discovery_task", task_id, input_url, _job_id=task_id)
            if enqueued:
                queued_count += 1
            else:
                skipped_count += 1

        await session.commit()
        if queued_count > 0:
            logger.info(f"[Server Mode] Scheduled pending sweep: queued {queued_count} boards ({skipped_count} skipped).")



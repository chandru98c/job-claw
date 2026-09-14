"""
ARQ discovery task: runs the Discovery Engine inside the worker infrastructure.

Flow:
  POST /tasks → PostgreSQL → Redis → ARQ → discovery_task → DiscoveryEngine → RawJobs

Emits structured TaskEvents throughout execution.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.database.database import AsyncSessionLocal
from app.database.models import Task, TaskEvent, TaskStatus, TaskEventType
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
from app.discovery.strategies.career_page import CareerPageStrategy
from app.discovery.strategies.robots import RobotsStrategy
from app.discovery.strategies.sitemap import SitemapStrategy

logger = logging.getLogger(__name__)


def build_registry() -> StrategyRegistry:
    """Build and populate the strategy registry at task startup."""
    registry = StrategyRegistry()
    registry.register(GreenhouseAdapter())
    registry.register(LeverAdapter())
    registry.register(AshbyAdapter())
    registry.register(WorkableAdapter())
    registry.register(SmartRecruitersAdapter())
    registry.register(CareerPageStrategy())
    registry.register(RobotsStrategy())
    registry.register(SitemapStrategy())
    return registry


async def discovery_task(ctx, task_id: str, input_url: str):
    """
    ARQ worker task for running job discovery.
    """
    logger.info(f"Starting discovery_task for task_id={task_id}, url={input_url}")

    # ─── Task State: RUNNING ────────────────────────────────────────
    async with AsyncSessionLocal() as session:
        # Check Worker Mode First
        redis = ctx.get('redis')
        if redis:
            mode_bytes = await redis.get("worker:mode")
            if mode_bytes and mode_bytes.decode("utf-8") == "server":
                logger.info("Worker is in SERVER mode. Local discovery is disabled. Skipping task.")
                return "Skipped: Worker in SERVER mode"

        task = await session.get(Task, task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found in database")

        if task.status in (TaskStatus.SUCCEEDED, TaskStatus.CANCELLED):
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

        discovery_result = await engine.discover(input_url)

        # ─── Task State: SUCCEEDED ──────────────────────────────────
        async with AsyncSessionLocal() as session:
            task = await session.get(Task, task_id)
            if task and task.status not in (TaskStatus.CANCELLED, TaskStatus.SUCCEEDED, TaskStatus.FAILED):
                task.status = TaskStatus.SUCCEEDED
                task.finished_at = datetime.now(timezone.utc)
                task.metrics = {
                    "jobs_discovered": len(discovery_result.raw_jobs),
                    "accounting": discovery_result.accounting,
                }
                await session.commit()
                await log_event(session, task_id, TaskEventType.COMPLETED, {
                    "jobs_discovered": len(discovery_result.raw_jobs),
                })

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
        raise

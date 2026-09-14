import logging
from arq.connections import RedisSettings
from app.core.config import settings
from app.workers.tasks import dummy_discovery_task
from app.workers.discovery import discovery_task
from app.workers.canonicalize import canonicalize_job_task
from app.workers.verification import verify_job_task
from app.workers.reconciliation import reconcile_stuck_tasks
from app.workers.application import prepare_application_task, submit_application_task
from app.workers.saved_search import execute_saved_search_task, scheduled_saved_searches

from arq.cron import cron

logger = logging.getLogger(__name__)

# ARQ expects a dict or RedisSettings object for redis configuration
redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

async def startup(ctx):
    logger.info("Worker starting up...")
    # Run reconciliation on startup to catch tasks that were left RUNNING when the worker previously crashed.
    await reconcile_stuck_tasks()

async def shutdown(ctx):
    logger.info("Worker shutting down...")

class WorkerSettings:
    """
    Configuration for the ARQ worker.
    Start with: arq app.workers.settings.WorkerSettings
    """
    redis_settings = redis_settings
    functions = [
        dummy_discovery_task, 
        discovery_task, 
        canonicalize_job_task, 
        verify_job_task,
        prepare_application_task,
        submit_application_task,
        execute_saved_search_task
    ]
    cron_jobs = [
        cron(scheduled_saved_searches, minute=0) # Run every hour
    ]
    on_startup = startup
    on_shutdown = shutdown
    
    max_tries = settings.WORKER_MAX_TRIES
    job_timeout = settings.WORKER_JOB_TIMEOUT
    max_jobs = settings.WORKER_CONCURRENCY
    
    # Crucial for cancellation support (cooperative cancellation via asyncio.CancelledError)
    allow_abort_jobs = True

import asyncio
import uuid
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update, delete
from app.database.database import AsyncSessionLocal
from app.database.models import Source, Job, Task, TaskStatus, JobSourceProvenance
from app.workers.discovery import scheduled_registry_discovery, discovery_task
from app.main import app
from arq.connections import RedisSettings, create_pool
from app.workers.settings import WorkerSettings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_worker_briefly(redis_pool, redis_settings):
    from arq.worker import Worker
    worker = Worker(
        functions=WorkerSettings.functions,
        redis_settings=redis_settings,
        ctx={"redis": redis_pool},
        max_jobs=5,
        job_timeout=60,
    )
    task = asyncio.create_task(worker.main())
    
    for _ in range(15):
        queued_count = await redis_pool.zcard("arq:queue")
        in_progress = await redis_pool.zcard("arq:in-progress")
        if queued_count == 0 and in_progress == 0:
            break
        await asyncio.sleep(1)
        
    await asyncio.sleep(3)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def main():
    test_db = 1
    logger.info("=== REDIS CONFIGURATION ===")
    logger.info(f"Redis host: {WorkerSettings.redis_settings.host}")
    logger.info(f"Redis port: {WorkerSettings.redis_settings.port}")
    logger.info(f"Redis DB: {test_db} (ISOLATED TEST DB)")
    logger.info("===========================")

    test_redis_settings = RedisSettings(
        host=WorkerSettings.redis_settings.host,
        port=WorkerSettings.redis_settings.port,
        database=test_db,
    )

    redis = await create_pool(test_redis_settings)
    await redis.flushdb()

    async with AsyncSessionLocal() as session:
        await session.execute(update(Source).values(is_active=False))
        
        airbnb = (await session.execute(select(Source).where(Source.domain == "airbnb.com"))).scalar_one_or_none()
        if not airbnb:
            logger.error("Airbnb source not found in DB.")
            return
            
        airbnb.is_active = True
        airbnb.circuit_status = "CLOSED"
        await session.commit()
        
        from app.database.models import TaskEvent
        await session.execute(delete(TaskEvent))
        await session.execute(delete(JobSourceProvenance).where(JobSourceProvenance.source_id == airbnb.id))
        await session.execute(delete(Task).where(Task.worker_type == "discovery_task"))
        await session.commit()
        
    logger.info("=== VERIFYING LOCAL MODE (AUTOMATIC SCHEDULER) ===")
    await redis.set("worker:mode", "local")
    
    ctx = {"redis": redis}
    await scheduled_registry_discovery(ctx)
    
    queued_count = await redis.zcard("arq:queue")
    logger.info(f"Local mode queued count from automatic schedule: {queued_count}")
    assert queued_count == 0, "Local mode should not automatically enqueue tasks!"
    
    logger.info("=== VERIFYING MANUAL DISCOVERY (LOCAL MODE) ===")
    # Manual trigger simulates enqueueing directly
    manual_task_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as session:
        new_task = Task(
            id=manual_task_id,
            worker_type="discovery_task",
            status=TaskStatus.QUEUED,
            target_id=airbnb.id
        )
        session.add(new_task)
        await session.commit()
    
    await redis.enqueue_job("discovery_task", manual_task_id, airbnb.start_url)
    
    logger.info("=== STARTING WORKER TO PROCESS MANUAL TASK ===")
    await run_worker_briefly(redis, test_redis_settings)
    
    async with AsyncSessionLocal() as session:
        manual_prov = (await session.execute(
            select(JobSourceProvenance).where(JobSourceProvenance.source_id == airbnb.id)
        )).scalars().all()
        logger.info(f"Manual discovery jobs persisted: {len(manual_prov)}")
        assert len(manual_prov) > 0, "Manual discovery failed to execute or persist!"

    # Clean up for server mode test
    await redis.flushdb()
    async with AsyncSessionLocal() as session:
        from app.database.models import TaskEvent
        await session.execute(delete(TaskEvent))
        await session.execute(delete(JobSourceProvenance).where(JobSourceProvenance.source_id == airbnb.id))
        await session.execute(delete(Task).where(Task.worker_type == "discovery_task"))
        
        # Reset rate limiting to allow enqueueing again
        airbnb.last_attempt_at = None
        airbnb.last_success_at = None
        airbnb.last_run_at = None
        await session.commit()

    logger.info("=== VERIFYING SERVER MODE (AUTOMATIC SCHEDULER) ===")
    await redis.set("worker:mode", "server")
    
    await scheduled_registry_discovery(ctx)
    
    queued_count = await redis.zcard("arq:queue")
    logger.info(f"Server mode queued count from automatic schedule: {queued_count}")
    assert queued_count > 0, "Server mode MUST automatically enqueue tasks!"
    
    logger.info("=== STARTING WORKER TO PROCESS TASKS ===")
    await run_worker_briefly(redis, test_redis_settings)
    
    logger.info("=== VERIFYING DATABASE PERSISTENCE ===")
    async with AsyncSessionLocal() as session:
        jobs_count = (await session.execute(
            select(JobSourceProvenance).where(JobSourceProvenance.source_id == airbnb.id)
        )).scalars().all()
        
        logger.info(f"Jobs persisted for airbnb: {len(jobs_count)}")
        assert len(jobs_count) > 0, "Worker failed to persist jobs for the enqueued task!"
        
        for prov in jobs_count[:5]:
            # Load canonical job
            res = await session.execute(select(Job).where(Job.id == prov.job_id))
            canon_job = res.scalar_one()
            logger.info(f"source_id: {prov.source_id}")
            logger.info(f"source_job_id: {prov.source_job_id}")
            logger.info(f"job title: {canon_job.title}")
            logger.info(f"canonical job ID: {canon_job.id}")
            logger.info(f"provenance ID: {prov.id}")
            logger.info(f"discovery method: {prov.source_type}")
            logger.info(f"apply URL: {canon_job.canonical_apply_url}")
            logger.info("---")

    logger.info("SUCCESS: Server Mode and Local Mode runtime verified.")

if __name__ == "__main__":
    asyncio.run(main())

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from app.database.models import Task, TaskStatus, Source, CircuitStatus
from app.workers.discovery import discovery_task
from app.database.database import AsyncSessionLocal
from app.schemas.discovery import StrategyExecutionResult, DiscoveryError, DiscoveryErrorType
from app.discovery.engine import DiscoveryResult

@pytest.mark.asyncio
async def test_discovery_task_circuit_breaker_flow(async_db_session, monkeypatch):
    """
    Test that the discovery task respects and updates circuit breaker state.
    """
    import uuid
    from sqlalchemy import delete
    source_id = f"cb_test_source_{uuid.uuid4().hex[:8]}"
    task_id = f"cb_test_task_{uuid.uuid4().hex[:8]}"

    # 1. Create a dummy Source
    source = Source(
        id=source_id,
        domain=f"cbtest-{uuid.uuid4().hex[:8]}.com",
        ats_type="ats",
        is_active=True,
        circuit_status=CircuitStatus.CLOSED,
        consecutive_failures=0
    )
    async_db_session.add(source)
    
    # 2. Create a dummy Task linked to this source
    task = Task(
        id=task_id,
        target_id=source_id,
        worker_type="discovery_task",
        status=TaskStatus.QUEUED
    )
    async_db_session.add(task)
    await async_db_session.commit()
    
    # Mock the DiscoveryEngine to return success
    class MockEngineSuccess:
        def __init__(self, *args, **kwargs):
            pass
        async def discover(self, input_url: str, source_config=None):
            from app.schemas.discovery import RawJob, DiscoveryProvenanceDTO
            res = DiscoveryResult(input_url=input_url, success=True)
            provenance = DiscoveryProvenanceDTO(
                source_id=source_id,
                strategy_id="mock_strategy",
                source_type="ats",
                source_url="https://cbtest.com",
                source_job_id="1"
            )
            res.raw_jobs = [RawJob(
                title="Software Engineer", 
                company="MockCo", 
                location="Remote",
                provenance=provenance
            )]
            return res
            
    monkeypatch.setattr("app.workers.discovery.DiscoveryEngine", MockEngineSuccess)
    
    # Run task
    result = await discovery_task({}, task_id, "https://cbtest.com")
    assert "Discovered 1 jobs" in result
    
    # Refresh and check state
    await async_db_session.refresh(source)
    assert source.circuit_status == CircuitStatus.CLOSED
    assert source.consecutive_failures == 0
    assert source.last_success_at is not None
    
    # Now simulate failures
    class MockEngineFailure:
        def __init__(self, *args, **kwargs):
            pass
        async def discover(self, input_url: str, source_config=None):
            res = DiscoveryResult(input_url=input_url, success=False)
            res.errors = [
                DiscoveryError(error_type=DiscoveryErrorType.NETWORK_FAILURE, message="HTTP 404 Not Found")
            ]
            return res
            
    monkeypatch.setattr("app.workers.discovery.DiscoveryEngine", MockEngineFailure)
    
    # Reset task for next run by creating a new one
    task2 = Task(id=f"cb_test_task_{uuid.uuid4().hex[:8]}", target_id=source_id, worker_type="discovery_task", status=TaskStatus.QUEUED)
    async_db_session.add(task2)
    await async_db_session.commit()
    
    # Fail 1
    result = await discovery_task({}, task2.id, "https://cbtest.com")
    assert "Failed with 1 errors" in result
    await async_db_session.refresh(source)
    assert source.consecutive_failures == 1
    assert source.circuit_status == CircuitStatus.CLOSED
    assert source.last_error == "HTTP 404 Not Found"
    
    # Fail 2
    task3 = Task(id=f"cb_test_task_{uuid.uuid4().hex[:8]}", target_id=source_id, worker_type="discovery_task", status=TaskStatus.QUEUED)
    async_db_session.add(task3)
    await async_db_session.commit()
    await discovery_task({}, task3.id, "https://cbtest.com")
    await async_db_session.refresh(source)
    assert source.consecutive_failures == 2
    assert source.circuit_status == CircuitStatus.CLOSED
    
    # Fail 3 -> Trips breaker
    task4 = Task(id=f"cb_test_task_{uuid.uuid4().hex[:8]}", target_id=source_id, worker_type="discovery_task", status=TaskStatus.QUEUED)
    async_db_session.add(task4)
    await async_db_session.commit()
    await discovery_task({}, task4.id, "https://cbtest.com")
    await async_db_session.refresh(source)
    assert source.consecutive_failures == 3
    assert source.circuit_status == CircuitStatus.OPEN
    assert source.next_retry_at is not None
    assert source.next_retry_at > datetime.now(timezone.utc)
    
    # Next run should be skipped
    task5 = Task(id=f"cb_test_task_{uuid.uuid4().hex[:8]}", target_id=source_id, worker_type="discovery_task", status=TaskStatus.QUEUED)
    async_db_session.add(task5)
    await async_db_session.commit()
    result = await discovery_task({}, task5.id, "https://cbtest.com")
    assert "Skipped: Circuit OPEN" in result
    
    # Force cooldown expiry to test HALF_OPEN claim
    source.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await async_db_session.commit()
    
    # Also mock engine to succeed this time to test HALF_OPEN -> CLOSED recovery
    monkeypatch.setattr("app.workers.discovery.DiscoveryEngine", MockEngineSuccess)
    
    task6 = Task(id=f"cb_test_task_{uuid.uuid4().hex[:8]}", target_id=source_id, worker_type="discovery_task", status=TaskStatus.QUEUED)
    async_db_session.add(task6)
    await async_db_session.commit()
    result = await discovery_task({}, task6.id, "https://cbtest.com")
    assert "Discovered 1 jobs" in result
    
    await async_db_session.refresh(source)
    assert source.circuit_status == CircuitStatus.CLOSED
    assert source.consecutive_failures == 0
    assert source.last_error is None

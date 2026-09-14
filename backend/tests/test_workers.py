import pytest
import asyncio
from unittest import mock
from app.database.models import Task, TaskStatus, TaskEvent, TaskEventType
from app.workers.tasks import dummy_discovery_task
from app.workers.reconciliation import reconcile_stuck_tasks

# Mock db for workers
class MockSession:
    def __init__(self):
        self.added = []
        self.tasks = {}
        
    async def get(self, model, id):
        return self.tasks.get(id)
        
    def add(self, obj):
        self.added.append(obj)
        
    async def commit(self):
        pass
        
    async def execute(self, stmt):
        tasks_list = list(self.tasks.values())
        class Result:
            def scalars(self):
                class Scalars:
                    def all(self):
                        return [t for t in tasks_list if getattr(t, "status", None) == TaskStatus.RUNNING]
                return Scalars()
        return Result()

    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

@pytest.fixture
def mock_db():
    session = MockSession()
    with mock.patch("app.workers.tasks.AsyncSessionLocal", return_value=session), \
         mock.patch("app.workers.reconciliation.AsyncSessionLocal", return_value=session):
        yield session

@pytest.mark.asyncio
async def test_dummy_task_success(mock_db):
    task = Task(id="test-123", status=TaskStatus.QUEUED)
    mock_db.tasks["test-123"] = task
    
    ctx = {"job_try": 1}
    # Mock asyncio.sleep to run fast
    with mock.patch("asyncio.sleep", new_callable=mock.AsyncMock):
        result = await dummy_discovery_task(ctx, "test-123", "target-abc")
        
    assert result == "Success"
    assert task.status == TaskStatus.SUCCEEDED
    
    # Check events (STARTED, 5x PROGRESS, COMPLETED)
    events = [e for e in mock_db.added if isinstance(e, TaskEvent)]
    assert any(e.event_type == TaskEventType.STARTED for e in events)
    assert any(e.event_type == TaskEventType.COMPLETED for e in events)
    assert len([e for e in events if e.event_type == TaskEventType.PROGRESS]) == 5

@pytest.mark.asyncio
async def test_dummy_task_idempotency(mock_db):
    # Already SUCCEEDED
    task = Task(id="test-123", status=TaskStatus.SUCCEEDED)
    mock_db.tasks["test-123"] = task
    
    result = await dummy_discovery_task({"job_try": 1}, "test-123", "target-abc")
    assert result == "Skipped: Already finished"
    assert len(mock_db.added) == 0 # no new events

@pytest.mark.asyncio
async def test_dummy_task_failure_and_retry(mock_db):
    task = Task(id="test-123", status=TaskStatus.QUEUED)
    mock_db.tasks["test-123"] = task
    
    # 1. Simulate Failure (attempt 1 out of 3, should go to RETRYING)
    with mock.patch("asyncio.sleep", side_effect=Exception("Boom")):
        with pytest.raises(Exception):
            await dummy_discovery_task({"job_try": 1}, "test-123", "target-abc")
            
    assert task.status == TaskStatus.RETRYING
    assert task.error == "Boom"
    
    # 2. Simulate Retry
    with mock.patch("asyncio.sleep", new_callable=mock.AsyncMock):
        result = await dummy_discovery_task({"job_try": 2}, "test-123", "target-abc")
        
    assert result == "Success"
    assert task.status == TaskStatus.SUCCEEDED
    assert task.retry_count == 1
    
    events = [e for e in mock_db.added if isinstance(e, TaskEvent)]
    assert any(e.event_type == TaskEventType.RETRY for e in events)

@pytest.mark.asyncio
async def test_dummy_task_cancellation(mock_db):
    task = Task(id="test-123", status=TaskStatus.QUEUED)
    mock_db.tasks["test-123"] = task
    
    with mock.patch("asyncio.sleep", side_effect=asyncio.CancelledError()):
        with pytest.raises(asyncio.CancelledError):
            await dummy_discovery_task({"job_try": 1}, "test-123", "target-abc")
            
    assert task.status == TaskStatus.CANCELLED
    
    events = [e for e in mock_db.added if isinstance(e, TaskEvent)]
    assert any(e.event_type == TaskEventType.CANCELLED for e in events)

@pytest.mark.asyncio
async def test_reconciliation_stuck_tasks(mock_db):
    task1 = Task(id="1", status=TaskStatus.RUNNING)
    task2 = Task(id="2", status=TaskStatus.QUEUED)
    mock_db.tasks = {"1": task1, "2": task2}
    
    await reconcile_stuck_tasks()
    
    assert task1.status == TaskStatus.FAILED
    assert "Worker crashed unexpectedly" in task1.error
    assert task2.status == TaskStatus.QUEUED # Unaffected
    
    events = [e for e in mock_db.added if isinstance(e, TaskEvent)]
    assert len(events) == 1
    assert events[0].event_type == TaskEventType.ERROR

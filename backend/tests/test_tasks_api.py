import pytest
import asyncio
from unittest import mock
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database.models import Task, TaskStatus, TaskEvent, TaskEventType

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

class MockRedisPool:
    async def enqueue_job(self, function, *args, **kwargs):
        # Return a mock job
        class MockJob:
            pass
        return MockJob()
        
    async def close(self):
        pass

class MockJob:
    def __init__(self, task_id, redis):
        pass
    async def abort(self):
        return True # Simulate success

# Mock db dependency
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
        
    async def refresh(self, obj):
        pass
        
    async def execute(self, stmt):
        class Result:
            def scalars(self):
                class Scalars:
                    def all(self):
                        return []
                return Scalars()
        return Result()

@pytest.fixture(autouse=True)
def setup_app_state():
    app.state.redis = MockRedisPool()

@pytest.fixture
def override_get_db():
    session = MockSession()
    from app.database.database import get_db
    app.dependency_overrides[get_db] = lambda: session
    yield session
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_enqueue_task(client, override_get_db):
    response = await client.post("/tasks/", params={"target_id": "test-target"})
    assert response.status_code == 201
    data = response.json()
    assert "task_id" in data
    assert data["status"] == "QUEUED"
    
    # Check if added to DB
    tasks = [obj for obj in override_get_db.added if isinstance(obj, Task)]
    assert len(tasks) == 1
    assert tasks[0].target_id == "test-target"

@pytest.mark.asyncio
async def test_get_task(client, override_get_db):
    # Missing
    response = await client.get("/tasks/non-existent")
    assert response.status_code == 404
    
    # Exists
    task = Task(id="test-123", status=TaskStatus.RUNNING, worker_type="dummy", target_id="target")
    override_get_db.tasks["test-123"] = task
    
    response = await client.get("/tasks/test-123")
    assert response.status_code == 200
    assert response.json()["status"] == "RUNNING"

@pytest.mark.asyncio
async def test_cancel_task(client, override_get_db):
    task = Task(id="test-123", status=TaskStatus.RUNNING, worker_type="dummy")
    override_get_db.tasks["test-123"] = task
    
    with mock.patch("arq.jobs.Job", return_value=MockJob("test-123", None)):
        response = await client.post("/tasks/test-123/cancel")
        assert response.status_code == 200
        assert task.status == TaskStatus.CANCELLED
        
    # Test cancelling already completed
    task.status = TaskStatus.SUCCEEDED
    response = await client.post("/tasks/test-123/cancel")
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_sse_generator():
    from app.api.sse import event_stream
    
    class MockRequest:
        async def is_disconnected(self):
            return False
            
    request = MockRequest()
    task = Task(id="test-123", status=TaskStatus.RUNNING)
    
    event1 = TaskEvent(id="e1", task_id="test-123", event_type=TaskEventType.QUEUED)
    event2 = TaskEvent(id="e2", task_id="test-123", event_type=TaskEventType.COMPLETED)
    
    class MockResult:
        def scalars(self):
            class Scalars:
                def all(self):
                    return [event1, event2]
            return Scalars()

    mock_session = mock.AsyncMock()
    mock_session.get = mock.AsyncMock(return_value=task)
    mock_session.execute = mock.AsyncMock(return_value=MockResult())
    mock_session.refresh = mock.AsyncMock()

    # Create a proper async context manager for AsyncSessionLocal
    mock_session_ctx = mock.AsyncMock()
    mock_session_ctx.__aenter__ = mock.AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = mock.AsyncMock(return_value=False)

    with mock.patch("app.database.database.AsyncSessionLocal", return_value=mock_session_ctx):
        gen = event_stream("test-123", request)
        messages = []
        
        async for msg in gen:
            messages.append(msg)
            
        assert len(messages) == 3
        assert "QUEUED" in messages[0]
        assert "COMPLETED" in messages[1]
        assert "DONE" in messages[2]


import pytest
import uuid
import json
import asyncio
from datetime import datetime, timezone
from app.main import app
from httpx import AsyncClient, ASGITransport
import app.database.database as db_module
from app.database.models import Task, TaskEvent, TaskStatus, TaskEventType

@pytest.fixture
def mock_disconnect(monkeypatch):
    # Fix ASGITransport not sending disconnect
    import starlette.requests
    async def always_disconnected(self):
        # If the client disconnected, we'd normally know. 
        # For tests, we just say false until the test finishes.
        return False
    monkeypatch.setattr(starlette.requests.Request, "is_disconnected", always_disconnected)

@pytest.mark.asyncio
async def test_sse_reliability_and_replay():
    task_id = f"test_task_{uuid.uuid4().hex[:8]}"
    transport = ASGITransport(app=app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Setup task and first event
        async with db_module.AsyncSessionLocal() as db:
            new_task = Task(id=task_id, worker_type="sse_test", status=TaskStatus.RUNNING, created_at=datetime.now(timezone.utc))
            event1 = TaskEvent(id=str(uuid.uuid4()), task_id=task_id, event_type=TaskEventType.STARTED, payload={"msg": "1"}, created_at=datetime.now(timezone.utc))
            db.add(new_task)
            db.add(event1)
            await db.commit()
            
        # 2. Connect client and read first event
        received_events = []
        
        # We will run a background task to write COMPLETED after 1 second
        # so the server stream terminates naturally and doesn't hang pytest-asyncio!
        async def delayed_complete():
            await asyncio.sleep(1)
            async with db_module.AsyncSessionLocal() as db:
                event2 = TaskEvent(id=str(uuid.uuid4()), task_id=task_id, event_type=TaskEventType.PROGRESS, payload={"msg": "2"}, created_at=datetime.now(timezone.utc))
                event3 = TaskEvent(id=str(uuid.uuid4()), task_id=task_id, event_type=TaskEventType.COMPLETED, payload={"msg": "3"}, created_at=datetime.now(timezone.utc))
                db.add(event2)
                db.add(event3)
                t = await db.get(Task, task_id)
                t.status = TaskStatus.SUCCEEDED
                await db.commit()
                
        bg_task = asyncio.create_task(delayed_complete())
        
        async with client.stream("GET", f"/sse/tasks/{task_id}/events/stream") as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    event_data = json.loads(data_str)
                    received_events.append(event_data)
                    # Don't break, wait for the stream to close naturally from the COMPLETED event
        
        await bg_task
        
        # We should have received all events because we stayed connected
        event_types = [e.get("event_type") for e in received_events if "event_type" in e]
        assert "STARTED" in event_types
        assert "PROGRESS" in event_types
        assert "COMPLETED" in event_types
        
        # 3. Disconnect happens when context manager exits. 
        # Reconnect and verify replay of durable events!
        reconnect_events = []
        async with client.stream("GET", f"/sse/tasks/{task_id}/events/stream") as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    event_data = json.loads(data_str)
                    reconnect_events.append(event_data)
        
        replayed_types = [e.get("event_type") for e in reconnect_events if "event_type" in e]
        assert "STARTED" in replayed_types
        assert "PROGRESS" in replayed_types
        assert "COMPLETED" in replayed_types
        assert reconnect_events[-1].get("status") == "DONE"
        assert len(replayed_types) == 3

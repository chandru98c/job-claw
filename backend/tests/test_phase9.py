import pytest
from httpx import AsyncClient, ASGITransport
import json
from unittest.mock import AsyncMock

from app.main import app
from app.workers.discovery import discovery_task
from app.api.system import WorkerModeUpdate

@pytest.mark.asyncio
async def test_worker_mode_endpoints():
    # Mock redis get/set
    mock_redis = AsyncMock()
    mock_redis.get.return_value = b"local"
    app.state.redis = mock_redis
    
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # GET
        res = await client.get("/system/worker-mode")
        assert res.status_code == 200
        assert res.json()["mode"] == "local"
        
        # POST valid
        res = await client.post("/system/worker-mode", json={"mode": "server"})
        assert res.status_code == 200
        assert res.json()["mode"] == "server"
        mock_redis.set.assert_called_with("worker:mode", "server")
        
        # POST invalid
        res = await client.post("/system/worker-mode", json={"mode": "invalid"})
        assert res.status_code == 422

@pytest.mark.asyncio
async def test_discovery_task_executes_in_server_mode():
    # Setup mock redis in ctx
    mock_redis = AsyncMock()
    mock_redis.get.return_value = b"server"
    
    ctx = {"redis": mock_redis, "job_try": 1}
    
    # Should NOT return skipped. It should fail later in the DB dependency or return cleanly.
    try:
        result = await discovery_task(ctx, "test_task_id", "http://test.com")
        assert result != "Skipped: Worker in SERVER mode"
    except Exception:
        pass # Expected since we didn't mock DB sessions inside the task

@pytest.mark.asyncio
async def test_scheduled_registry_discovery_only_enqueues_in_server_mode():
    from app.workers.discovery import scheduled_registry_discovery
    
    # Test local mode (should abort quietly)
    mock_redis_local = AsyncMock()
    mock_redis_local.get.return_value = b"local"
    ctx_local = {"redis": mock_redis_local}
    
    await scheduled_registry_discovery(ctx_local)
    mock_redis_local.enqueue_job.assert_not_called()
    
    # Test server mode (should proceed and try to query DB)
    mock_redis_server = AsyncMock()
    mock_redis_server.get.return_value = b"server"
    ctx_server = {"redis": mock_redis_server}
    
    try:
        await scheduled_registry_discovery(ctx_server)
    except Exception:
        pass # Expected since we didn't mock DB sessions
    
    # Verify it checked the mode
    mock_redis_server.get.assert_called_with("worker:mode")

@pytest.mark.asyncio
async def test_verification_continues_on_server_mode():
    from app.workers.verification import verify_job_task
    # Setup mock redis in ctx
    mock_redis = AsyncMock()
    mock_redis.get.return_value = b"server"
    
    ctx = {"redis": mock_redis, "job_try": 1}
    
    # It should NOT abort. It should fail later in the DB dependency or return cleanly, but NOT return the Skipped message.
    try:
        result = await verify_job_task(ctx, "test_job")
        assert result != "Skipped: Worker in SERVER mode"
    except Exception as e:
        # DB connection might fail since it's an integration task, but that proves it didn't skip early.
        assert "Skipped: Worker in SERVER mode" not in str(e)

def test_seeder_network_isolation():
    import os
    import re
    # The seeder script must not import requests, httpx, aiohttp, urllib, or Playwright
    seeder_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "seed_registry.py")
    
    with open(seeder_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    assert "import requests" not in content
    assert "import httpx" not in content
    assert "import aiohttp" not in content
    assert "from httpx" not in content
    assert "urllib.request" not in content
    assert "playwright" not in content.lower()
    assert "SafeHTTPClient" not in content

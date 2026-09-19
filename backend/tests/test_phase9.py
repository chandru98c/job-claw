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
async def test_discovery_task_aborts_on_server_mode():
    # Setup mock redis in ctx
    mock_redis = AsyncMock()
    mock_redis.get.return_value = b"server"
    
    ctx = {"redis": mock_redis, "job_try": 1}
    
    # Should return skipped without querying DB
    result = await discovery_task(ctx, "test_task_id", "http://test.com")
    assert result == "Skipped: Worker in SERVER mode"
    mock_redis.get.assert_called_with("worker:mode")

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

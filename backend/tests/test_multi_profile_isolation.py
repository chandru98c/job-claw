import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock
from app.main import app

@pytest.mark.asyncio
async def test_multi_profile_isolation():
    app.state.redis = AsyncMock()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as async_client:
        # 1. Create Profile A
        res_a = await async_client.post("/profiles", json={"name": "Profile A"})
        assert res_a.status_code == 200
        profile_a_id = res_a.json()["id"]

        # 2. Create Profile B
        res_b = await async_client.post("/profiles", json={"name": "Profile B"})
        assert res_b.status_code == 200
        profile_b_id = res_b.json()["id"]

        # 3. Create Saved Search as Profile A
        headers_a = {"X-Profile-ID": profile_a_id}
        res_search = await async_client.post("/saved-searches", json={
            "name": "Search A",
            "query": "Engineer",
            "location": "NY",
            "remote": True,
            "enabled": True
        }, headers=headers_a)
        assert res_search.status_code == 201
        search_id = res_search.json()["id"]

        # 4. Profile A can read its own search
        res_read_a = await async_client.get(f"/saved-searches/{search_id}", headers=headers_a)
        assert res_read_a.status_code == 200
        assert res_read_a.json()["name"] == "Search A"

        # 5. Profile B CANNOT read Profile A's search
        headers_b = {"X-Profile-ID": profile_b_id}
        res_read_b = await async_client.get(f"/saved-searches/{search_id}", headers=headers_b)
        assert res_read_b.status_code == 404  # Expected: The query scoped by profile_id won't find it

        # 6. Profile B CANNOT update Profile A's search
        res_update_b = await async_client.patch(f"/saved-searches/{search_id}", json={"name": "Hacked"}, headers=headers_b)
        assert res_update_b.status_code == 404

        # 7. Invalid Profile ID returns 404 (due to get_valid_profile validation)
        headers_invalid = {"X-Profile-ID": "00000000-0000-0000-0000-000000000000"}
        res_invalid = await async_client.get("/saved-searches", headers=headers_invalid)
        assert res_invalid.status_code == 404

        # 8. Profile B CANNOT run Profile A's search (Concurrency check)
        res_run_b = await async_client.post(f"/saved-searches/{search_id}/run", headers=headers_b)
        assert res_run_b.status_code == 404

        # 9. Duplicate Run protection on Profile A
        res_run_a1 = await async_client.post(f"/saved-searches/{search_id}/run", headers=headers_a)
        assert res_run_a1.status_code == 202
        
        # Try immediately running again to verify lock/duplicate handling
        res_run_a2 = await async_client.post(f"/saved-searches/{search_id}/run", headers=headers_a)
        assert res_run_a2.status_code == 202
        assert res_run_a2.json().get("message") == "Saved search is already running"

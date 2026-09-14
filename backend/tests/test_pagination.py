"""
Tests for BoundedPaginator.
"""
import pytest
from unittest import mock

from app.discovery.pagination import BoundedPaginator
from app.discovery.budget import ResourceAccounting, ResourceBudget
from app.core.http import SafeHTTPClient

@pytest.fixture
def accounting():
    budget = ResourceBudget(max_requests=10, max_pages=10)
    return ResourceAccounting(budget)

@pytest.mark.asyncio
async def test_bounded_pagination_normal(accounting):
    paginator = BoundedPaginator(max_pages=3)
    
    call_count = 0
    async def mock_fetch(url, client):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return (f"http://example.com/page{call_count+1}", [1, 2], f"hash{call_count}")
        return (None, [1], "hash3")
        
    client = mock.AsyncMock(spec=SafeHTTPClient)
    result = await paginator.paginate("http://example.com/page1", client, accounting, mock_fetch)
    
    assert result.pages_fetched == 3
    assert result.items_extracted == 5
    assert result.success is True
    assert accounting.requests_attempted == 3

@pytest.mark.asyncio
async def test_bounded_pagination_cycle_detection(accounting):
    paginator = BoundedPaginator(max_pages=10)
    
    async def mock_fetch(url, client):
        # Always return the same next URL
        return ("http://example.com/page1", [1], "hash_unique_so_it_doesnt_stop")
        
    client = mock.AsyncMock(spec=SafeHTTPClient)
    # Even if stop_on_repeated_content is False, cycle detection (visited_urls) should catch it
    paginator.stop_on_repeated_content = False
    result = await paginator.paginate("http://example.com/page1", client, accounting, mock_fetch)
    
    assert result.pages_fetched == 1
    assert result.success is True

@pytest.mark.asyncio
async def test_bounded_pagination_repeated_content(accounting):
    paginator = BoundedPaginator(max_pages=10)
    
    call_count = 0
    async def mock_fetch(url, client):
        nonlocal call_count
        call_count += 1
        # Return different URL but same content hash
        return (f"http://example.com/page{call_count+1}", [1], "same_hash")
        
    client = mock.AsyncMock(spec=SafeHTTPClient)
    result = await paginator.paginate("http://example.com/page1", client, accounting, mock_fetch)
    
    assert result.pages_fetched == 2

@pytest.mark.asyncio
async def test_bounded_pagination_no_new_items(accounting):
    paginator = BoundedPaginator(max_pages=10)
    
    async def mock_fetch(url, client):
        # Empty items list
        return ("http://example.com/page2", [], "hash")
        
    client = mock.AsyncMock(spec=SafeHTTPClient)
    result = await paginator.paginate("http://example.com/page1", client, accounting, mock_fetch)
    
    assert result.pages_fetched == 1
    assert result.items_extracted == 0

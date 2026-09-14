"""
Bounded pagination helper for discovery strategies.

Provides a robust, deterministic way to paginate through resources,
respecting limits, budget, duplicate-page detection, and cycle protection.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Awaitable, Any, Optional

from app.core.http import SafeHTTPClient
from app.discovery.budget import ResourceAccounting

logger = logging.getLogger(__name__)

class PaginationResult:
    def __init__(self):
        self.pages_fetched: int = 0
        self.items_extracted: int = 0
        self.success: bool = True
        self.errors: list[str] = []

class BoundedPaginator:
    """
    Handles bounded deterministic pagination.
    """
    def __init__(
        self,
        max_pages: int = 5,
        stop_on_repeated_content: bool = True,
        stop_when_no_new_items: bool = True,
    ):
        self.max_pages = max_pages
        self.stop_on_repeated_content = stop_on_repeated_content
        self.stop_when_no_new_items = stop_when_no_new_items

    async def paginate(
        self,
        initial_url: str,
        http_client: SafeHTTPClient,
        accounting: ResourceAccounting,
        fetch_page_func: Callable[[str, SafeHTTPClient], Awaitable[tuple[Optional[str], list[Any], Optional[str]]]],
    ) -> PaginationResult:
        """
        fetch_page_func should take (url, http_client) and return:
        (next_url, items, page_content_hash)
        """
        result = PaginationResult()
        visited_urls: set[str] = set()
        seen_content_hashes: set[str] = set()
        current_url = initial_url

        while current_url and result.pages_fetched < self.max_pages:
            if not accounting.can_paginate():
                logger.info("Pagination stopped: budget exhausted.")
                break

            # Cycle detection
            if current_url in visited_urls:
                logger.warning(f"Pagination stopped: cycle detected at {current_url}")
                break
            
            visited_urls.add(current_url)

            try:
                next_url, items, content_hash = await fetch_page_func(current_url, http_client)
                accounting.record_request(success=True)
                result.pages_fetched += 1
                result.items_extracted += len(items)

                # Stop on repeated content
                if self.stop_on_repeated_content and content_hash:
                    if content_hash in seen_content_hashes:
                        logger.info("Pagination stopped: repeated content detected.")
                        break
                    seen_content_hashes.add(content_hash)

                # Stop when no new items
                if self.stop_when_no_new_items and not items:
                    logger.info("Pagination stopped: no items on page.")
                    break

                current_url = next_url

            except Exception as e:
                accounting.record_request(success=False)
                logger.error(f"Pagination error at {current_url}: {e}")
                result.success = False
                result.errors.append(str(e))
                break

        return result

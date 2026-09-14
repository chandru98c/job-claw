"""
Resource budget tracker for bounded discovery execution.

Every discovery run has explicit limits. When any budget is exhausted,
the engine must stop cleanly — never continue indefinitely.
"""
from __future__ import annotations

import time
import logging
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ResourceBudget(BaseModel):
    """Configurable limits for a single discovery execution."""
    max_requests: int = Field(default=50, ge=1)
    max_bytes_downloaded: int = Field(default=20 * 1024 * 1024, ge=1)  # 20 MB
    max_sitemap_depth: int = Field(default=3, ge=1)
    max_sitemap_documents: int = Field(default=10, ge=1)
    max_sitemap_urls: int = Field(default=500, ge=1)
    max_candidate_urls: int = Field(default=30, ge=1)
    max_pages: int = Field(default=5, ge=1)
    max_duration_seconds: float = Field(default=120.0, ge=1.0)


class ResourceAccounting:
    """
    Tracks resource consumption during a discovery run.
    All methods are synchronous and fast — no I/O.
    """

    def __init__(self, budget: ResourceBudget):
        self.budget = budget
        self._start_time = time.monotonic()

        # Counters
        self.requests_attempted: int = 0
        self.requests_successful: int = 0
        self.bytes_downloaded: int = 0
        self.sitemap_documents_processed: int = 0
        self.sitemap_urls_inspected: int = 0
        self.candidates_generated: int = 0
        self.candidates_rejected: int = 0
        self.jobs_discovered: int = 0

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._start_time

    # ─── Budget Checks ──────────────────────────────────────────────────

    def can_request(self) -> bool:
        return (
            self.requests_attempted < self.budget.max_requests
            and self.elapsed_seconds < self.budget.max_duration_seconds
        )

    def can_process_sitemap(self) -> bool:
        return (
            self.sitemap_documents_processed < self.budget.max_sitemap_documents
            and self.can_request()
        )

    def can_extract_sitemap_urls(self) -> bool:
        return self.sitemap_urls_inspected < self.budget.max_sitemap_urls

    def can_generate_candidate(self) -> bool:
        return self.candidates_generated < self.budget.max_candidate_urls

    def can_paginate(self) -> bool:
        return self.can_request()

    def is_expired(self) -> bool:
        return self.elapsed_seconds >= self.budget.max_duration_seconds

    # ─── Recording ──────────────────────────────────────────────────────

    def record_request(self, response_bytes: int = 0, success: bool = True):
        self.requests_attempted += 1
        self.bytes_downloaded += response_bytes
        if success:
            self.requests_successful += 1

    def record_sitemap_document(self):
        self.sitemap_documents_processed += 1

    def record_sitemap_urls(self, count: int):
        self.sitemap_urls_inspected += count

    def record_candidate(self, rejected: bool = False):
        self.candidates_generated += 1
        if rejected:
            self.candidates_rejected += 1

    def record_jobs(self, count: int):
        self.jobs_discovered += count

    # ─── Summary ────────────────────────────────────────────────────────

    def summary(self) -> dict:
        return {
            "requests_attempted": self.requests_attempted,
            "requests_successful": self.requests_successful,
            "bytes_downloaded": self.bytes_downloaded,
            "sitemap_documents_processed": self.sitemap_documents_processed,
            "sitemap_urls_inspected": self.sitemap_urls_inspected,
            "candidates_generated": self.candidates_generated,
            "candidates_rejected": self.candidates_rejected,
            "jobs_discovered": self.jobs_discovered,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
        }

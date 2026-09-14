"""
Career Page Discovery Strategy.

Generates bounded deterministic candidates for common career page paths,
then probes them via SafeHTTPClient to find live career endpoints.

Does NOT aggressively scrape — only discovers endpoints.
Does NOT assume every HTTP 200 is a valid job source.
"""
from __future__ import annotations

import time
import logging
import urllib.parse
from typing import Optional

from app.discovery.interfaces import DiscoveryStrategy, StrategyCategory
from app.schemas.discovery import (
    StrategyCandidate,
    StrategyExecutionResult,
    DiscoveryError,
    DiscoveryErrorType,
)
from app.core.http import SafeHTTPClient

logger = logging.getLogger(__name__)

# Bounded set of common career page paths
CAREER_PATHS = [
    "/careers",
    "/jobs",
    "/job",
    "/work-with-us",
    "/join-us",
    "/opportunities",
    "/employment",
    "/careers/",
    "/jobs/",
]


class CareerPageStrategy(DiscoveryStrategy):
    """
    Deterministic career page discovery.
    Generates candidates from a bounded set of common paths.
    """

    @property
    def strategy_id(self) -> str:
        return "career_page_discovery"

    @property
    def name(self) -> str:
        return "Career Page Discovery"

    @property
    def category(self) -> StrategyCategory:
        return StrategyCategory.HEURISTIC

    @property
    def priority(self) -> int:
        return 50  # Medium priority — ATS is higher

    @property
    def capabilities(self) -> dict:
        return {
            "discovers_endpoints": True,
            "extracts_jobs": False,  # Only discovers, does not extract
            "max_candidates": len(CAREER_PATHS),
        }

    def recognizes_url(self, url: str) -> bool:
        """Recognizes any HTTP/HTTPS URL with a hostname."""
        try:
            parsed = urllib.parse.urlparse(url)
            return parsed.scheme in ("http", "https") and bool(parsed.hostname)
        except Exception:
            return False

    def generate_candidates(self, url: str) -> list[StrategyCandidate]:
        """
        Generate career page candidates from the input URL's origin.
        Produces at most len(CAREER_PATHS) candidates.
        """
        try:
            parsed = urllib.parse.urlparse(url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return []

        candidates = []
        for path in CAREER_PATHS:
            candidate_url = origin + path
            candidates.append(
                StrategyCandidate(
                    strategy_id=self.strategy_id,
                    target_url=candidate_url,
                    evidence=f"Common career path: {path}",
                    confidence=0.3,
                    source="deterministic_path_probe",
                    priority=self.priority,
                )
            )
        return candidates

    async def execute(
        self,
        candidate: StrategyCandidate,
        http_client: SafeHTTPClient,
    ) -> StrategyExecutionResult:
        """
        Probe a career page candidate to check if it's a live career endpoint.
        Returns metadata about the endpoint — does NOT extract individual jobs.
        """
        start = time.monotonic()
        result = StrategyExecutionResult(
            strategy_id=self.strategy_id,
            candidate_id=candidate.candidate_id,
        )

        try:
            url = candidate.validated_url or candidate.target_url
            response = await http_client.get(url)
            result.requests_attempted = 1

            # Check for career-related content signals
            body_lower = response.decode("utf-8", errors="replace").lower()[:10000]
            career_signals = [
                "career", "job", "position", "opening", "vacancy",
                "apply", "hiring", "employment", "opportunity",
            ]
            signal_count = sum(1 for s in career_signals if s in body_lower)

            if signal_count >= 2:
                result.success = True
                result.jobs_discovered = 0  # Endpoint discovered, not jobs
            else:
                result.success = True
                result.jobs_discovered = 0

        except Exception as e:
            result.requests_attempted = 1
            result.success = False
            result.errors.append(
                DiscoveryError(
                    error_type=DiscoveryErrorType.NETWORK_FAILURE,
                    strategy_id=self.strategy_id,
                    candidate_id=candidate.candidate_id,
                    message=str(e),
                )
            )

        result.duration_seconds = time.monotonic() - start
        return result

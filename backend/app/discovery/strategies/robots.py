"""
robots.txt Discovery Strategy.

Fetches and parses robots.txt for Sitemap directives.
All extracted URLs pass through the CandidatePipeline before execution.

Does NOT blindly crawl every URL in robots.txt.
Only extracts Sitemap directives.
"""
from __future__ import annotations

import time
import logging
import urllib.parse

from app.discovery.interfaces import DiscoveryStrategy, StrategyCategory
from app.schemas.discovery import (
    StrategyCandidate,
    StrategyExecutionResult,
    DiscoveryError,
    DiscoveryErrorType,
)
from app.core.http import SafeHTTPClient

logger = logging.getLogger(__name__)

MAX_SITEMAP_DIRECTIVES = 20


def parse_robots_txt(content: str) -> list[str]:
    """
    Parse robots.txt content and extract Sitemap directives.
    Returns a bounded list of sitemap URLs (not validated).
    """
    sitemaps: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        if line.lower().startswith("sitemap:"):
            url = line[len("sitemap:"):].strip()
            if url:
                sitemaps.append(url)
        if len(sitemaps) >= MAX_SITEMAP_DIRECTIVES:
            break
    return sitemaps


class RobotsStrategy(DiscoveryStrategy):
    """
    Discovers sitemaps via robots.txt.
    The execute() method fetches robots.txt and stores discovered sitemap
    URLs in the result metadata. The Discovery Engine reads these and
    creates new candidates for the SitemapStrategy.
    """

    @property
    def strategy_id(self) -> str:
        return "robots_txt_discovery"

    @property
    def name(self) -> str:
        return "robots.txt Discovery"

    @property
    def category(self) -> StrategyCategory:
        return StrategyCategory.HEURISTIC

    @property
    def priority(self) -> int:
        return 40

    @property
    def capabilities(self) -> dict:
        return {"discovers_sitemaps": True, "extracts_jobs": False}

    def recognizes_url(self, url: str) -> bool:
        try:
            parsed = urllib.parse.urlparse(url)
            return parsed.scheme in ("http", "https") and bool(parsed.hostname)
        except Exception:
            return False

    def generate_candidates(self, url: str) -> list[StrategyCandidate]:
        try:
            parsed = urllib.parse.urlparse(url)
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        except Exception:
            return []

        return [
            StrategyCandidate(
                strategy_id=self.strategy_id,
                target_url=robots_url,
                evidence="Standard robots.txt location",
                confidence=0.6,
                source="deterministic_robots",
                priority=self.priority,
            )
        ]

    async def execute(
        self,
        candidate: StrategyCandidate,
        http_client: SafeHTTPClient,
    ) -> StrategyExecutionResult:
        """
        Fetch robots.txt and extract Sitemap directives.
        Discovered sitemaps are stored in result metadata for the engine.
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

            content = response.decode("utf-8", errors="replace")
            sitemaps = parse_robots_txt(content)

            result.success = True
            result.jobs_discovered = 0
            # Stash discovered sitemaps for engine consumption
            result._discovered_sitemaps = sitemaps

        except Exception as e:
            result.requests_attempted = 1
            result.success = False
            result._discovered_sitemaps = []
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

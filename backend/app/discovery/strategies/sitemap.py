"""
Sitemap Discovery Strategy.

Discovers and processes XML sitemaps with explicit resource limits:
  - maximum depth (for sitemap index nesting)
  - maximum documents processed
  - maximum URLs extracted
  - cycle detection (visited set)
  - bounded response size (via SafeHTTPClient policy)

Classifies sitemap URLs using deterministic signals (path keywords,
known ATS domains) to identify likely job-related endpoints.
"""
from __future__ import annotations

import time
import logging
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Optional

from app.discovery.interfaces import DiscoveryStrategy, StrategyCategory
from app.discovery.budget import ResourceAccounting
from app.schemas.discovery import (
    StrategyCandidate,
    StrategyExecutionResult,
    DiscoveryError,
    DiscoveryErrorType,
)
from app.core.http import SafeHTTPClient

logger = logging.getLogger(__name__)

# Job-related URL path keywords for classification
JOB_URL_KEYWORDS = {
    "job", "jobs", "career", "careers", "position", "positions",
    "opening", "openings", "vacancy", "vacancies", "opportunity",
    "opportunities", "hiring", "work", "employment", "apply",
    "greenhouse", "lever", "workday", "ashby", "breezy",
}

# XML namespace for sitemaps
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def classify_url_as_job_related(url: str) -> float:
    """
    Score a URL for job-relatedness using deterministic path signals.
    Returns 0.0–1.0 confidence. Does NOT make network requests.
    """
    try:
        parsed = urllib.parse.urlparse(url.lower())
        path_parts = parsed.path.split("/")
        hostname = parsed.hostname or ""
    except Exception:
        return 0.0

    score = 0.0
    matches = sum(1 for part in path_parts if part in JOB_URL_KEYWORDS)
    if matches >= 2:
        score = 0.8
    elif matches == 1:
        score = 0.5

    # Boost for known ATS domains
    ats_domains = ["greenhouse.io", "lever.co", "workday.com", "ashbyhq.com"]
    if any(hostname.endswith(d) for d in ats_domains):
        score = max(score, 0.9)

    return min(score, 1.0)


def parse_sitemap_xml(content: bytes) -> tuple[list[str], list[str]]:
    """
    Parse a sitemap XML document.
    Returns (sitemap_index_urls, page_urls).
    Handles both sitemap indexes and regular sitemaps.
    Fails gracefully on malformed XML.
    """
    sitemap_index_urls: list[str] = []
    page_urls: list[str] = []

    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        logger.warning("Failed to parse sitemap XML")
        return [], []

    # Strip namespace for easier matching
    tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

    if tag == "sitemapindex":
        # Sitemap index — extract child sitemap URLs
        for sitemap_elem in root.findall("sm:sitemap", SITEMAP_NS):
            loc = sitemap_elem.find("sm:loc", SITEMAP_NS)
            if loc is not None and loc.text:
                sitemap_index_urls.append(loc.text.strip())
        # Try without namespace too (some sites omit it)
        if not sitemap_index_urls:
            for sitemap_elem in root.findall("sitemap"):
                loc = sitemap_elem.find("loc")
                if loc is not None and loc.text:
                    sitemap_index_urls.append(loc.text.strip())

    elif tag == "urlset":
        # Regular sitemap — extract page URLs
        for url_elem in root.findall("sm:url", SITEMAP_NS):
            loc = url_elem.find("sm:loc", SITEMAP_NS)
            if loc is not None and loc.text:
                page_urls.append(loc.text.strip())
        if not page_urls:
            for url_elem in root.findall("url"):
                loc = url_elem.find("loc")
                if loc is not None and loc.text:
                    page_urls.append(loc.text.strip())

    return sitemap_index_urls, page_urls


class SitemapStrategy(DiscoveryStrategy):
    """
    Sitemap discovery with bounded traversal.
    Discovers sitemaps, processes indexes, classifies URLs.
    """

    @property
    def strategy_id(self) -> str:
        return "sitemap_discovery"

    @property
    def name(self) -> str:
        return "Sitemap Discovery"

    @property
    def category(self) -> StrategyCategory:
        return StrategyCategory.SITEMAP

    @property
    def priority(self) -> int:
        return 60

    @property
    def capabilities(self) -> dict:
        return {
            "discovers_sitemaps": True,
            "supports_sitemap_index": True,
            "classifies_job_urls": True,
        }

    def recognizes_url(self, url: str) -> bool:
        """Recognizes any HTTP/HTTPS URL (sitemap is a standard location)."""
        try:
            parsed = urllib.parse.urlparse(url)
            return parsed.scheme in ("http", "https") and bool(parsed.hostname)
        except Exception:
            return False

    def generate_candidates(self, url: str) -> list[StrategyCandidate]:
        """Generate candidates for standard sitemap locations."""
        try:
            parsed = urllib.parse.urlparse(url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return []

        sitemap_paths = ["/sitemap.xml", "/sitemap_index.xml"]
        candidates = []
        for path in sitemap_paths:
            candidates.append(
                StrategyCandidate(
                    strategy_id=self.strategy_id,
                    target_url=origin + path,
                    evidence=f"Standard sitemap location: {path}",
                    confidence=0.5,
                    source="deterministic_sitemap",
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
        Fetch and parse a sitemap. If it's an index, recursively process
        child sitemaps within budget limits.

        Discovered job-related URLs are stored for engine consumption.
        """
        start = time.monotonic()
        result = StrategyExecutionResult(
            strategy_id=self.strategy_id,
            candidate_id=candidate.candidate_id,
        )

        visited: set[str] = set()
        job_urls: list[str] = []
        accounting = ResourceAccounting(
            budget=__import__("app.discovery.budget", fromlist=["ResourceBudget"]).ResourceBudget()
        )

        await self._process_sitemap(
            url=candidate.validated_url or candidate.target_url,
            http_client=http_client,
            visited=visited,
            job_urls=job_urls,
            accounting=accounting,
            depth=0,
            max_depth=3,
            result=result,
        )

        result.duration_seconds = time.monotonic() - start
        result._discovered_job_urls = job_urls
        return result

    async def _process_sitemap(
        self,
        url: str,
        http_client: SafeHTTPClient,
        visited: set,
        job_urls: list,
        accounting: ResourceAccounting,
        depth: int,
        max_depth: int,
        result: StrategyExecutionResult,
    ):
        """Recursively process sitemaps with strict bounds."""
        # Cycle detection
        if url in visited:
            return
        visited.add(url)

        # Depth limit
        if depth > max_depth:
            logger.warning(f"Sitemap depth limit reached at {url}")
            return

        # Budget checks
        if not accounting.can_request():
            logger.info("Request budget exhausted during sitemap crawl")
            return
        if not accounting.can_process_sitemap():
            logger.info("Sitemap document budget exhausted")
            return

        try:
            response = await http_client.get(url)
            accounting.record_request(len(response), success=True)
            accounting.record_sitemap_document()
            result.requests_attempted += 1

            sitemap_index_urls, page_urls = parse_sitemap_xml(response)

            # Process page URLs: classify and collect job-related ones
            for page_url in page_urls:
                if not accounting.can_extract_sitemap_urls():
                    break
                accounting.record_sitemap_urls(1)

                score = classify_url_as_job_related(page_url)
                if score >= 0.4:
                    job_urls.append(page_url)

            # Recurse into sitemap indexes
            for child_url in sitemap_index_urls:
                if not accounting.can_process_sitemap():
                    break
                await self._process_sitemap(
                    url=child_url,
                    http_client=http_client,
                    visited=visited,
                    job_urls=job_urls,
                    accounting=accounting,
                    depth=depth + 1,
                    max_depth=max_depth,
                    result=result,
                )

        except Exception as e:
            accounting.record_request(0, success=False)
            result.requests_attempted += 1
            result.errors.append(
                DiscoveryError(
                    error_type=DiscoveryErrorType.NETWORK_FAILURE,
                    strategy_id=self.strategy_id,
                    candidate_id=result.candidate_id,
                    message=f"Sitemap fetch failed for {url}: {e}",
                )
            )

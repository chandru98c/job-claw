"""
Comprehensive tests for Phase 5: Deterministic Job Discovery Engine.

All external HTTP is mocked. No live websites in automated tests.
"""
from __future__ import annotations

import pytest
import json
import xml.etree.ElementTree as ET
from unittest import mock

from app.discovery.engine import DiscoveryEngine, DiscoveryResult
from app.discovery.registry import StrategyRegistry
from app.discovery.pipeline import CandidatePipeline
from app.discovery.budget import ResourceBudget, ResourceAccounting
from app.discovery.strategies.career_page import CareerPageStrategy, CAREER_PATHS
from app.discovery.strategies.robots import RobotsStrategy, parse_robots_txt
from app.discovery.strategies.sitemap import (
    SitemapStrategy,
    parse_sitemap_xml,
    classify_url_as_job_related,
)
from app.discovery.adapters.greenhouse import GreenhouseAdapter
from app.core.http import SafeHTTPClient, DomainPolicy
from app.schemas.discovery import (
    StrategyCandidate,
    CandidateState,
)


# ═══════════════════════════════════════════════════════════════════════
# Test Helpers & Fixtures
# ═══════════════════════════════════════════════════════════════════════

MOCK_DNS = [(2, 1, 6, "", ("93.184.216.34", 0))]

def _mock_dns():
    return mock.patch("app.core.security._original_getaddrinfo", return_value=MOCK_DNS)


def _build_registry():
    reg = StrategyRegistry()
    reg.register(GreenhouseAdapter())
    reg.register(CareerPageStrategy())
    reg.register(RobotsStrategy())
    reg.register(SitemapStrategy())
    return reg


SAMPLE_SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/careers/engineering</loc></url>
  <url><loc>https://example.com/about</loc></url>
  <url><loc>https://example.com/jobs/12345</loc></url>
  <url><loc>https://boards.greenhouse.io/acme/jobs/99</loc></url>
</urlset>"""

SAMPLE_SITEMAP_INDEX = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-jobs.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-blog.xml</loc></sitemap>
</sitemapindex>"""

SAMPLE_ROBOTS = """User-agent: *
Disallow: /admin/

Sitemap: https://example.com/sitemap.xml
Sitemap: https://example.com/sitemap-jobs.xml
"""

GREENHOUSE_RESPONSE = json.dumps({
    "jobs": [
        {
            "id": 1,
            "title": "Software Engineer",
            "location": {"name": "NYC"},
            "content": "Build stuff",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
        }
    ]
}).encode("utf-8")


# ═══════════════════════════════════════════════════════════════════════
# Career Page Discovery Tests
# ═══════════════════════════════════════════════════════════════════════

class TestCareerPageStrategy:

    def test_recognizes_http_url(self):
        s = CareerPageStrategy()
        assert s.recognizes_url("https://example.com")
        assert s.recognizes_url("http://company.com/about")
        assert not s.recognizes_url("ftp://example.com")
        assert not s.recognizes_url("not a url")

    def test_generates_bounded_candidates(self):
        s = CareerPageStrategy()
        candidates = s.generate_candidates("https://example.com/about")
        assert len(candidates) == len(CAREER_PATHS)
        for c in candidates:
            assert c.state == CandidateState.DISCOVERED
            assert c.target_url.startswith("https://example.com/")

    def test_no_duplicate_origins(self):
        s = CareerPageStrategy()
        candidates = s.generate_candidates("https://example.com/deep/path/page")
        # All should use the origin only
        for c in candidates:
            assert "deep/path" not in c.target_url

    @pytest.mark.asyncio
    async def test_execute_with_career_signals(self):
        s = CareerPageStrategy()
        candidate = StrategyCandidate(
            strategy_id="career_page_discovery",
            target_url="https://example.com/careers",
            validated_url="https://example.com/careers",
            state=CandidateState.VALIDATED,
        )
        mock_client = mock.AsyncMock(spec=SafeHTTPClient)
        mock_client.get = mock.AsyncMock(
            return_value=b"<html>Join our team! See career opportunities and apply for open positions.</html>"
        )
        result = await s.execute(candidate, mock_client)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_network_failure(self):
        s = CareerPageStrategy()
        candidate = StrategyCandidate(
            strategy_id="career_page_discovery",
            target_url="https://example.com/careers",
            validated_url="https://example.com/careers",
            state=CandidateState.VALIDATED,
        )
        mock_client = mock.AsyncMock(spec=SafeHTTPClient)
        mock_client.get = mock.AsyncMock(side_effect=ConnectionError("timeout"))
        result = await s.execute(candidate, mock_client)
        assert result.success is False
        assert len(result.errors) == 1


# ═══════════════════════════════════════════════════════════════════════
# robots.txt Tests
# ═══════════════════════════════════════════════════════════════════════

class TestRobotsStrategy:

    def test_parse_robots_valid(self):
        sitemaps = parse_robots_txt(SAMPLE_ROBOTS)
        assert len(sitemaps) == 2
        assert "https://example.com/sitemap.xml" in sitemaps
        assert "https://example.com/sitemap-jobs.xml" in sitemaps

    def test_parse_robots_empty(self):
        sitemaps = parse_robots_txt("")
        assert sitemaps == []

    def test_parse_robots_malformed(self):
        sitemaps = parse_robots_txt("garbage\n!!!@@@\nno sitemaps here")
        assert sitemaps == []

    def test_parse_robots_multiple_directives(self):
        content = "\n".join(f"Sitemap: https://example.com/sitemap{i}.xml" for i in range(25))
        sitemaps = parse_robots_txt(content)
        assert len(sitemaps) == 20  # Bounded at 20

    def test_generates_robots_candidate(self):
        s = RobotsStrategy()
        candidates = s.generate_candidates("https://example.com/about")
        assert len(candidates) == 1
        assert candidates[0].target_url == "https://example.com/robots.txt"
        assert candidates[0].state == CandidateState.DISCOVERED

    @pytest.mark.asyncio
    async def test_execute_with_sitemaps(self):
        s = RobotsStrategy()
        candidate = StrategyCandidate(
            strategy_id="robots_txt_discovery",
            target_url="https://example.com/robots.txt",
            validated_url="https://example.com/robots.txt",
            state=CandidateState.VALIDATED,
        )
        mock_client = mock.AsyncMock(spec=SafeHTTPClient)
        mock_client.get = mock.AsyncMock(return_value=SAMPLE_ROBOTS.encode())
        result = await s.execute(candidate, mock_client)
        assert result.success is True
        assert hasattr(result, '_discovered_sitemaps')
        assert len(result._discovered_sitemaps) == 2

    @pytest.mark.asyncio
    async def test_execute_network_failure(self):
        s = RobotsStrategy()
        candidate = StrategyCandidate(
            strategy_id="robots_txt_discovery",
            target_url="https://example.com/robots.txt",
            validated_url="https://example.com/robots.txt",
            state=CandidateState.VALIDATED,
        )
        mock_client = mock.AsyncMock(spec=SafeHTTPClient)
        mock_client.get = mock.AsyncMock(side_effect=ConnectionError("fail"))
        result = await s.execute(candidate, mock_client)
        assert result.success is False


# ═══════════════════════════════════════════════════════════════════════
# Sitemap Tests
# ═══════════════════════════════════════════════════════════════════════

class TestSitemapParsing:

    def test_parse_regular_sitemap(self):
        index_urls, page_urls = parse_sitemap_xml(SAMPLE_SITEMAP)
        assert len(index_urls) == 0
        assert len(page_urls) == 4

    def test_parse_sitemap_index(self):
        index_urls, page_urls = parse_sitemap_xml(SAMPLE_SITEMAP_INDEX)
        assert len(index_urls) == 2
        assert len(page_urls) == 0

    def test_parse_malformed_xml(self):
        index_urls, page_urls = parse_sitemap_xml(b"<not valid xml!!!>")
        assert index_urls == []
        assert page_urls == []

    def test_parse_empty(self):
        index_urls, page_urls = parse_sitemap_xml(b"")
        assert index_urls == []
        assert page_urls == []

    def test_parse_html_not_xml(self):
        index_urls, page_urls = parse_sitemap_xml(b"<html><body>Not a sitemap</body></html>")
        assert index_urls == []
        assert page_urls == []


class TestSitemapUrlClassification:

    def test_job_url_keywords(self):
        assert classify_url_as_job_related("https://example.com/careers/jobs/123") >= 0.5
        assert classify_url_as_job_related("https://example.com/jobs/opening") >= 0.5

    def test_non_job_url(self):
        assert classify_url_as_job_related("https://example.com/about") < 0.4
        assert classify_url_as_job_related("https://example.com/blog/post") < 0.4

    def test_ats_domain_url(self):
        assert classify_url_as_job_related("https://boards.greenhouse.io/acme/jobs") >= 0.8

    def test_invalid_url(self):
        assert classify_url_as_job_related("") == 0.0


class TestSitemapStrategy:

    def test_generates_sitemap_candidates(self):
        s = SitemapStrategy()
        candidates = s.generate_candidates("https://example.com/about")
        assert len(candidates) == 2
        urls = [c.target_url for c in candidates]
        assert "https://example.com/sitemap.xml" in urls
        assert "https://example.com/sitemap_index.xml" in urls

    @pytest.mark.asyncio
    async def test_execute_simple_sitemap(self):
        s = SitemapStrategy()
        candidate = StrategyCandidate(
            strategy_id="sitemap_discovery",
            target_url="https://example.com/sitemap.xml",
            validated_url="https://example.com/sitemap.xml",
            state=CandidateState.VALIDATED,
        )
        mock_client = mock.AsyncMock(spec=SafeHTTPClient)
        mock_client.get = mock.AsyncMock(return_value=SAMPLE_SITEMAP)
        result = await s.execute(candidate, mock_client)
        assert result.success is True
        assert hasattr(result, '_discovered_job_urls')
        # Should find job-related URLs
        assert len(result._discovered_job_urls) >= 2

    @pytest.mark.asyncio
    async def test_execute_sitemap_index(self):
        """Tests that sitemap index children are recursively processed."""
        s = SitemapStrategy()
        candidate = StrategyCandidate(
            strategy_id="sitemap_discovery",
            target_url="https://example.com/sitemap_index.xml",
            validated_url="https://example.com/sitemap_index.xml",
            state=CandidateState.VALIDATED,
        )

        call_count = 0
        async def mock_get(url):
            nonlocal call_count
            call_count += 1
            if "sitemap_index" in url:
                return SAMPLE_SITEMAP_INDEX
            else:
                return SAMPLE_SITEMAP

        mock_client = mock.AsyncMock(spec=SafeHTTPClient)
        mock_client.get = mock.AsyncMock(side_effect=mock_get)
        result = await s.execute(candidate, mock_client)
        assert result.requests_attempted >= 2  # Index + at least one child

    @pytest.mark.asyncio
    async def test_cycle_detection(self):
        """A sitemap that references itself should not loop forever."""
        cyclic_sitemap = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap.xml</loc></sitemap>
</sitemapindex>"""

        s = SitemapStrategy()
        candidate = StrategyCandidate(
            strategy_id="sitemap_discovery",
            target_url="https://example.com/sitemap.xml",
            validated_url="https://example.com/sitemap.xml",
            state=CandidateState.VALIDATED,
        )
        mock_client = mock.AsyncMock(spec=SafeHTTPClient)
        mock_client.get = mock.AsyncMock(return_value=cyclic_sitemap)
        result = await s.execute(candidate, mock_client)
        # Should terminate cleanly despite the cycle
        assert result.requests_attempted == 1  # Only fetched once

    @pytest.mark.asyncio
    async def test_depth_limit(self):
        """Nested sitemap indexes should stop at max depth."""
        deep_index = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/level1.xml</loc></sitemap>
</sitemapindex>"""

        call_count = 0
        async def mock_get(url):
            nonlocal call_count
            call_count += 1
            # Each level returns another index pointing deeper
            return deep_index.replace(b"level1", f"level{call_count}".encode())

        s = SitemapStrategy()
        candidate = StrategyCandidate(
            strategy_id="sitemap_discovery",
            target_url="https://example.com/root.xml",
            validated_url="https://example.com/root.xml",
            state=CandidateState.VALIDATED,
        )
        mock_client = mock.AsyncMock(spec=SafeHTTPClient)
        mock_client.get = mock.AsyncMock(side_effect=mock_get)
        result = await s.execute(candidate, mock_client)
        # Should stop at max_depth=3, not recurse forever
        assert result.requests_attempted <= 5

    @pytest.mark.asyncio
    async def test_network_failure_graceful(self):
        s = SitemapStrategy()
        candidate = StrategyCandidate(
            strategy_id="sitemap_discovery",
            target_url="https://example.com/sitemap.xml",
            validated_url="https://example.com/sitemap.xml",
            state=CandidateState.VALIDATED,
        )
        mock_client = mock.AsyncMock(spec=SafeHTTPClient)
        mock_client.get = mock.AsyncMock(side_effect=ConnectionError("timeout"))
        result = await s.execute(candidate, mock_client)
        assert len(result.errors) >= 1


# ═══════════════════════════════════════════════════════════════════════
# Resource Budget Tests
# ═══════════════════════════════════════════════════════════════════════

class TestResourceBudget:

    def test_default_budget(self):
        b = ResourceBudget()
        assert b.max_requests >= 1
        assert b.max_sitemap_depth >= 1

    def test_accounting_initial_state(self):
        a = ResourceAccounting(ResourceBudget())
        assert a.requests_attempted == 0
        assert a.can_request() is True

    def test_request_budget_exhaustion(self):
        a = ResourceAccounting(ResourceBudget(max_requests=2))
        a.record_request(100)
        assert a.can_request() is True
        a.record_request(200)
        assert a.can_request() is False

    def test_sitemap_budget_exhaustion(self):
        a = ResourceAccounting(ResourceBudget(max_sitemap_documents=1))
        assert a.can_process_sitemap() is True
        a.record_sitemap_document()
        assert a.can_process_sitemap() is False

    def test_sitemap_url_budget(self):
        a = ResourceAccounting(ResourceBudget(max_sitemap_urls=3))
        a.record_sitemap_urls(2)
        assert a.can_extract_sitemap_urls() is True
        a.record_sitemap_urls(1)
        assert a.can_extract_sitemap_urls() is False

    def test_summary(self):
        a = ResourceAccounting(ResourceBudget())
        a.record_request(1000, success=True)
        a.record_jobs(5)
        summary = a.summary()
        assert summary["requests_attempted"] == 1
        assert summary["requests_successful"] == 1
        assert summary["bytes_downloaded"] == 1000
        assert summary["jobs_discovered"] == 5


# ═══════════════════════════════════════════════════════════════════════
# Security Tests
# ═══════════════════════════════════════════════════════════════════════

class TestDiscoverySecurity:

    def test_localhost_sitemap_rejected(self):
        reg = _build_registry()
        pipeline = CandidatePipeline(registry=reg)
        candidate = StrategyCandidate(
            strategy_id="sitemap_discovery",
            target_url="http://localhost/sitemap.xml",
        )
        result = pipeline.validate_candidate(candidate)
        assert result.state == CandidateState.REJECTED

    def test_private_ip_sitemap_rejected(self):
        reg = _build_registry()
        pipeline = CandidatePipeline(registry=reg)
        candidate = StrategyCandidate(
            strategy_id="sitemap_discovery",
            target_url="http://10.0.0.1/sitemap.xml",
        )
        result = pipeline.validate_candidate(candidate)
        assert result.state == CandidateState.REJECTED

    def test_credential_url_in_sitemap_rejected(self):
        reg = _build_registry()
        pipeline = CandidatePipeline(registry=reg)
        candidate = StrategyCandidate(
            strategy_id="sitemap_discovery",
            target_url="https://user:pass@example.com/sitemap.xml",
        )
        result = pipeline.validate_candidate(candidate)
        assert result.state == CandidateState.REJECTED

    def test_unsupported_scheme_rejected(self):
        reg = _build_registry()
        pipeline = CandidatePipeline(registry=reg)
        candidate = StrategyCandidate(
            strategy_id="sitemap_discovery",
            target_url="ftp://example.com/sitemap.xml",
        )
        result = pipeline.validate_candidate(candidate)
        assert result.state == CandidateState.REJECTED


# ═══════════════════════════════════════════════════════════════════════
# Discovery Engine Integration Tests
# ═══════════════════════════════════════════════════════════════════════

class TestDiscoveryEngine:

    @pytest.mark.asyncio
    async def test_greenhouse_url_produces_raw_jobs(self):
        """Full pipeline: Greenhouse URL → candidates → validation → execution → RawJobs."""
        registry = _build_registry()
        engine = DiscoveryEngine(registry=registry)

        with _mock_dns():
            with mock.patch("app.discovery.pipeline.SafeHTTPClient") as MockHTTP:
                mock_client = mock.AsyncMock()
                mock_client.get = mock.AsyncMock(return_value=GREENHOUSE_RESPONSE)
                mock_ctx = mock.AsyncMock()
                mock_ctx.__aenter__ = mock.AsyncMock(return_value=mock_client)
                mock_ctx.__aexit__ = mock.AsyncMock(return_value=None)
                MockHTTP.return_value = mock_ctx

                result = await engine.discover("https://boards.greenhouse.io/acme")

        assert len(result.raw_jobs) >= 1
        assert result.raw_jobs[0].title == "Software Engineer"
        assert result.raw_jobs[0].provenance.strategy_id == "greenhouse_ats"

    @pytest.mark.asyncio
    async def test_unknown_url_returns_candidates(self):
        """An unknown URL should still try career page and robots strategies."""
        registry = _build_registry()
        engine = DiscoveryEngine(registry=registry)

        with _mock_dns():
            with mock.patch("app.discovery.pipeline.SafeHTTPClient") as MockHTTP:
                mock_client = mock.AsyncMock()
                mock_client.get = mock.AsyncMock(return_value=b"<html>No careers here</html>")
                mock_ctx = mock.AsyncMock()
                mock_ctx.__aenter__ = mock.AsyncMock(return_value=mock_client)
                mock_ctx.__aexit__ = mock.AsyncMock(return_value=None)
                MockHTTP.return_value = mock_ctx

                result = await engine.discover("https://example.com")

        # Should have attempted multiple strategies
        assert len(result.results) > 0

    @pytest.mark.asyncio
    async def test_event_callback(self):
        """Verify the engine emits structured events."""
        events = []
        async def capture(event_type, payload):
            events.append((event_type, payload))

        registry = _build_registry()
        engine = DiscoveryEngine(registry=registry, event_callback=capture)

        with _mock_dns():
            with mock.patch("app.discovery.pipeline.SafeHTTPClient") as MockHTTP:
                mock_client = mock.AsyncMock()
                mock_client.get = mock.AsyncMock(return_value=GREENHOUSE_RESPONSE)
                mock_ctx = mock.AsyncMock()
                mock_ctx.__aenter__ = mock.AsyncMock(return_value=mock_client)
                mock_ctx.__aexit__ = mock.AsyncMock(return_value=None)
                MockHTTP.return_value = mock_ctx

                await engine.discover("https://boards.greenhouse.io/acme")

        event_types = [e[0] for e in events]
        assert "discovery_started" in event_types
        assert "candidates_generated" in event_types
        assert "discovery_completed" in event_types

    @pytest.mark.asyncio
    async def test_resource_budget_respected(self):
        """Engine stops when budget is exhausted."""
        registry = _build_registry()
        tight_budget = ResourceBudget(max_requests=1)
        engine = DiscoveryEngine(registry=registry, budget=tight_budget)

        with _mock_dns():
            with mock.patch("app.discovery.pipeline.SafeHTTPClient") as MockHTTP:
                mock_client = mock.AsyncMock()
                mock_client.get = mock.AsyncMock(return_value=b"<html></html>")
                mock_ctx = mock.AsyncMock()
                mock_ctx.__aenter__ = mock.AsyncMock(return_value=mock_client)
                mock_ctx.__aexit__ = mock.AsyncMock(return_value=None)
                MockHTTP.return_value = mock_ctx

                result = await engine.discover("https://example.com")

        # Should have stopped after 1 request
        total_requests = sum(r.requests_attempted for r in result.results)
        assert total_requests <= 2  # May execute 1 candidate before stopping

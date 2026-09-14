"""
Discovery Engine: orchestrates the full deterministic discovery pipeline.

Flow:
  1. Input URL
  2. ATS-first resolution (via StrategyRegistry)
  3. Career page discovery
  4. robots.txt → sitemap discovery
  5. Sitemap URL classification
  6. ATS adapter execution for matching candidates
  7. Bounded RawJob collection

All through the existing CandidatePipeline security boundary.
"""
from __future__ import annotations

import logging
from typing import Optional, Callable, Awaitable
from dataclasses import dataclass, field

from app.discovery.registry import StrategyRegistry
from app.discovery.pipeline import CandidatePipeline
from app.discovery.budget import ResourceBudget, ResourceAccounting
from app.discovery.strategies.robots import parse_robots_txt
from app.core.http import SafeHTTPClient, DomainPolicy
from app.core.security import UrlValidator, SSRFViolationError
from app.schemas.discovery import (
    StrategyCandidate,
    StrategyExecutionResult,
    RawJob,
    DiscoveryError,
    DiscoveryErrorType,
    CandidateState,
)

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryResult:
    """Complete result of a discovery engine run."""
    input_url: str
    raw_jobs: list[RawJob] = field(default_factory=list)
    results: list[StrategyExecutionResult] = field(default_factory=list)
    errors: list[DiscoveryError] = field(default_factory=list)
    accounting: dict = field(default_factory=dict)
    success: bool = True


class DiscoveryEngine:
    """
    Orchestrates deterministic job discovery.

    Priority order:
      1. Known ATS resolution (highest priority strategies)
      2. Direct career page discovery
      3. robots.txt discovery
      4. Sitemap discovery + index expansion
      5. Sitemap URL classification
      6. ATS adapter execution for discovered endpoints

    The engine uses the existing Phase 4 StrategyRegistry and CandidatePipeline.
    It NEVER bypasses security validation.
    """

    def __init__(
        self,
        registry: StrategyRegistry,
        domain_policy: Optional[DomainPolicy] = None,
        budget: Optional[ResourceBudget] = None,
        event_callback: Optional[Callable[[str, dict], Awaitable[None]]] = None,
    ):
        self._registry = registry
        self._domain_policy = domain_policy or DomainPolicy()
        self._budget = budget or ResourceBudget()
        self._pipeline = CandidatePipeline(
            registry=registry,
            domain_policy=self._domain_policy,
        )
        self._event_callback = event_callback

    async def _emit(self, event_type: str, payload: dict):
        """Emit a structured event if callback is registered."""
        if self._event_callback:
            try:
                await self._event_callback(event_type, payload)
            except Exception as e:
                logger.warning(f"Event callback failed: {e}")

    async def discover(self, input_url: str) -> DiscoveryResult:
        """
        Run the full deterministic discovery pipeline for an input URL.
        """
        result = DiscoveryResult(input_url=input_url)
        accounting = ResourceAccounting(self._budget)

        await self._emit("discovery_started", {"url": input_url})

        # ─── Phase 1: Generate all candidates from all strategies ────
        all_candidates = self._registry.find_candidates(input_url)
        accounting.record_candidate()  # Count the generation pass

        await self._emit("candidates_generated", {
            "count": len(all_candidates),
            "strategies": list({c.strategy_id for c in all_candidates}),
        })

        if not all_candidates:
            result.errors.append(
                DiscoveryError(
                    error_type=DiscoveryErrorType.UNSUPPORTED_SOURCE,
                    message=f"No strategies recognized the input URL: {input_url}",
                )
            )
            result.success = False
            result.accounting = accounting.summary()
            await self._emit("discovery_completed", {"success": False})
            return result

        # ─── Phase 2: Validate candidates through security pipeline ──
        validated, rejected = self._pipeline.validate_candidates(all_candidates)

        for r in rejected:
            accounting.record_candidate(rejected=True)
            await self._emit("candidate_rejected", {
                "candidate_id": r.candidate_id,
                "strategy_id": r.strategy_id,
                "url": r.target_url,
            })

        await self._emit("candidates_validated", {
            "validated": len(validated),
            "rejected": len(rejected),
        })

        # ─── Phase 3: Execute validated candidates in priority order ─
        discovered_sitemap_urls: list[str] = []
        discovered_job_urls: list[str] = []

        for candidate in sorted(validated, key=lambda c: c.priority):
            if not accounting.can_request():
                logger.info("Request budget exhausted")
                break
            if accounting.is_expired():
                logger.info("Time budget exhausted")
                break

            await self._emit("strategy_started", {
                "strategy_id": candidate.strategy_id,
                "candidate_id": candidate.candidate_id,
                "url": candidate.target_url,
            })

            exec_result = await self._pipeline.execute_candidate(candidate)
            result.results.append(exec_result)
            accounting.record_request(success=exec_result.success)

            # Collect RawJobs from ATS adapters
            if exec_result.raw_jobs:
                result.raw_jobs.extend(exec_result.raw_jobs)
                accounting.record_jobs(len(exec_result.raw_jobs))
                await self._emit("jobs_extracted", {
                    "strategy_id": candidate.strategy_id,
                    "count": len(exec_result.raw_jobs),
                })

            # Collect discovered sitemaps from robots.txt strategy
            if hasattr(exec_result, '_discovered_sitemaps'):
                for sm_url in exec_result._discovered_sitemaps:
                    discovered_sitemap_urls.append(sm_url)
                    await self._emit("sitemap_discovered", {"url": sm_url})

            # Collect discovered job URLs from sitemap strategy
            if hasattr(exec_result, '_discovered_job_urls'):
                discovered_job_urls.extend(exec_result._discovered_job_urls)

            # Collect errors
            result.errors.extend(exec_result.errors)

        # ─── Phase 4: Process discovered sitemap URLs ────────────────
        if discovered_sitemap_urls and accounting.can_request():
            await self._process_discovered_sitemaps(
                discovered_sitemap_urls,
                result,
                accounting,
                discovered_job_urls,
            )

        # ─── Phase 5: Try ATS adapters on discovered job URLs ────────
        if discovered_job_urls and accounting.can_request():
            await self._try_ats_on_discovered_urls(
                discovered_job_urls,
                result,
                accounting,
            )

        result.accounting = accounting.summary()
        result.success = len(result.errors) == 0 or len(result.raw_jobs) > 0

        await self._emit("discovery_completed", {
            "success": result.success,
            "jobs_discovered": len(result.raw_jobs),
            "accounting": result.accounting,
        })

        return result

    async def _process_discovered_sitemaps(
        self,
        sitemap_urls: list[str],
        result: DiscoveryResult,
        accounting: ResourceAccounting,
        discovered_job_urls: list[str],
    ):
        """Process sitemap URLs discovered from robots.txt."""
        sitemap_strategy = self._registry.get("sitemap_discovery")
        if not sitemap_strategy:
            return

        for sm_url in sitemap_urls:
            if not accounting.can_request():
                break

            # Create and validate a candidate for this sitemap URL
            candidate = StrategyCandidate(
                strategy_id="sitemap_discovery",
                target_url=sm_url,
                evidence="Discovered via robots.txt Sitemap directive",
                confidence=0.7,
                source="robots_txt",
                priority=60,
            )

            validated_candidate = self._pipeline.validate_candidate(candidate)
            if validated_candidate.state != CandidateState.VALIDATED:
                accounting.record_candidate(rejected=True)
                continue

            accounting.record_candidate()
            exec_result = await self._pipeline.execute_candidate(validated_candidate)
            result.results.append(exec_result)
            accounting.record_request(success=exec_result.success)

            if hasattr(exec_result, '_discovered_job_urls'):
                discovered_job_urls.extend(exec_result._discovered_job_urls)

    async def _try_ats_on_discovered_urls(
        self,
        job_urls: list[str],
        result: DiscoveryResult,
        accounting: ResourceAccounting,
    ):
        """
        Try matching discovered URLs against ATS adapters in the registry.
        Only process URLs that match a registered ATS adapter.
        """
        for job_url in job_urls:
            if not accounting.can_request():
                break

            # Check if any ATS adapter recognizes this URL
            ats_candidates = self._registry.find_candidates(job_url)
            ats_candidates = [
                c for c in ats_candidates
                if c.strategy_id != "sitemap_discovery"
                and c.strategy_id != "robots_txt_discovery"
                and c.strategy_id != "career_page_discovery"
            ]

            if not ats_candidates:
                continue

            # Validate and execute
            for candidate in ats_candidates:
                if not accounting.can_request():
                    break

                validated = self._pipeline.validate_candidate(candidate)
                if validated.state != CandidateState.VALIDATED:
                    accounting.record_candidate(rejected=True)
                    continue

                accounting.record_candidate()
                exec_result = await self._pipeline.execute_candidate(validated)
                result.results.append(exec_result)
                accounting.record_request(success=exec_result.success)

                if exec_result.raw_jobs:
                    result.raw_jobs.extend(exec_result.raw_jobs)
                    accounting.record_jobs(len(exec_result.raw_jobs))

                result.errors.extend(exec_result.errors)

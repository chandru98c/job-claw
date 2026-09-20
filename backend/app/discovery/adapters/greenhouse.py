"""
Greenhouse ATS Adapter.

Greenhouse boards expose a public JSON API at:
  https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs

This adapter:
  - Recognizes supported Greenhouse board/API URL patterns
  - Extracts the board token (company identifier)
  - Constructs ONLY known-safe Greenhouse API URLs
  - Validates every constructed URL through the CandidatePipeline
  - Uses ONLY the SafeHTTPClient injected by the pipeline
  - Produces bounded RawJob objects
"""
import json
import re
import time
import logging
from typing import Optional
from datetime import datetime, timezone

from app.discovery.interfaces import ATSAdapter
from app.schemas.discovery import (
    StrategyCandidate,
    StrategyExecutionResult,
    RawJob,
    DiscoveryProvenanceDTO,
    DiscoveryError,
    DiscoveryErrorType,
    CandidateState,
    SourceConfig,
    MAX_TITLE_LEN,
    MAX_COMPANY_LEN,
    MAX_LOCATION_LEN,
    MAX_DESCRIPTION_LEN,
)
from app.core.http import SafeHTTPClient

logger = logging.getLogger(__name__)

# ─── Greenhouse URL Patterns ────────────────────────────────────────────────

# Pattern 1: boards-api.greenhouse.io/v1/boards/{token}/jobs
_API_PATTERN = re.compile(
    r"^https?://boards-api\.greenhouse\.io/v1/boards/([a-zA-Z0-9_-]+)/jobs",
    re.IGNORECASE,
)

# Pattern 2: boards.greenhouse.io/{token} (public career board)
_BOARD_PATTERN = re.compile(
    r"^https?://boards\.greenhouse\.io/([a-zA-Z0-9_-]+)(?:/.*)?$",
    re.IGNORECASE,
)

# Pattern 3: {company}.greenhouse.io (custom subdomain board)
_SUBDOMAIN_PATTERN = re.compile(
    r"^https?://([a-zA-Z0-9_-]+)\.greenhouse\.io(?:/.*)?$",
    re.IGNORECASE,
)

# Subdomains that are NOT board tokens (infrastructure domains)
_GREENHOUSE_RESERVED = {"boards", "boards-api", "www", "api", "app", "support"}


class GreenhouseAdapter(ATSAdapter):
    """
    ATS adapter for Greenhouse job boards.

    Recognizes Greenhouse URLs, constructs the canonical API endpoint,
    and parses the JSON response into bounded RawJob objects.
    """

    @property
    def strategy_id(self) -> str:
        return "greenhouse_ats"

    @property
    def name(self) -> str:
        return "Greenhouse ATS Adapter"

    @property
    def ats_name(self) -> str:
        return "Greenhouse"

    @property
    def priority(self) -> int:
        return 10  # High priority for known ATS

    @property
    def capabilities(self) -> dict:
        return {
            "supports_pagination": False,  # API returns all jobs at once
            "supports_json_api": True,
            "max_jobs_per_request": 500,
        }

    def extract_board_identifier(self, url: str) -> Optional[str]:
        """Extract the Greenhouse board token from a recognized URL."""
        # Try API URL first
        match = _API_PATTERN.match(url)
        if match:
            return match.group(1)

        # Try board URL
        match = _BOARD_PATTERN.match(url)
        if match:
            return match.group(1)

        # Try subdomain
        match = _SUBDOMAIN_PATTERN.match(url)
        if match:
            token = match.group(1).lower()
            if token not in _GREENHOUSE_RESERVED:
                return token

        return None

    def recognizes_url(self, url: str) -> bool:
        """Returns True if the URL matches a known Greenhouse pattern."""
        return self.extract_board_identifier(url) is not None

    def generate_candidates(self, url: str = None, source: SourceConfig = None) -> list[StrategyCandidate]:
        """
        Generate a candidate for the canonical Greenhouse API endpoint.
        Uses explicit source configuration if provided, otherwise infers from URL.
        """
        source_id = None
        if source and source.identifier:
            board_token = source.identifier
            source_id = source.source_id
        elif url:
            board_token = self.extract_board_identifier(url)
        else:
            return []
            
        if not board_token:
            return []

        # Construct the canonical, known-safe API URL
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"

        return [
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=api_url,
                evidence=f"Greenhouse board token: {board_token}",
                confidence=0.95 if url else 1.0,
                source="url_pattern_match" if url else "source_config",
                source_id=source_id,
                priority=self.priority,
            )
        ]

    async def execute(
        self,
        candidate: StrategyCandidate,
        http_client: SafeHTTPClient,
    ) -> StrategyExecutionResult:
        """
        Execute the Greenhouse API request and extract jobs.

        Pre-conditions (enforced by pipeline):
          - candidate.state == VALIDATED
          - http_client is SafeHTTPClient
        """
        start_time = time.monotonic()
        result = StrategyExecutionResult(
            strategy_id=self.strategy_id,
            adapter_id=self.strategy_id,
            candidate_id=candidate.candidate_id,
        )

        try:
            # Fetch using the validated URL
            url = candidate.validated_url or candidate.target_url
            response_data = await http_client.get(url)
            result.requests_attempted = 1

            # Parse jobs
            raw_jobs = await self.extract_jobs(response_data, candidate)
            result.raw_jobs = raw_jobs
            result.jobs_discovered = len(raw_jobs)

        except Exception as e:
            logger.error(f"Greenhouse adapter failed for {candidate.candidate_id}: {e}")
            result.success = False
            result.requests_attempted = 1
            error_type = DiscoveryErrorType.NETWORK_FAILURE
            if "parse" in str(e).lower() or "json" in str(e).lower():
                error_type = DiscoveryErrorType.PARSING_FAILURE
            result.errors.append(
                DiscoveryError(
                    error_type=error_type,
                    strategy_id=self.strategy_id,
                    adapter_id=self.strategy_id,
                    candidate_id=candidate.candidate_id,
                    message=str(e),
                )
            )

        result.duration_seconds = time.monotonic() - start_time
        return result

    async def extract_jobs(
        self,
        response_data: bytes,
        candidate: StrategyCandidate,
    ) -> list[RawJob]:
        """
        Parse Greenhouse API JSON response into bounded RawJob objects.

        Expected Greenhouse API response format:
        {
          "jobs": [
            {
              "id": 123,
              "title": "...",
              "location": {"name": "..."},
              "content": "...",
              "absolute_url": "...",
              "departments": [...],
              "metadata": [...]
            }
          ]
        }
        """
        try:
            data = json.loads(response_data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Greenhouse: failed to parse JSON: {e}")
            return []

        if not isinstance(data, dict):
            logger.warning("Greenhouse: response is not a JSON object")
            return []

        jobs_list = data.get("jobs", [])
        if not isinstance(jobs_list, list):
            logger.warning("Greenhouse: 'jobs' is not a list")
            return []

        raw_jobs: list[RawJob] = []

        for job_data in jobs_list:
            try:
                if not isinstance(job_data, dict):
                    continue

                # Extract and bound fields
                title = str(job_data.get("title", ""))[:MAX_TITLE_LEN]
                if not title:
                    continue  # Skip jobs without titles

                job_id = str(job_data.get("id", ""))
                absolute_url = str(job_data.get("absolute_url", ""))[:2048]
                apply_url = absolute_url or None

                # Location
                location_data = job_data.get("location", {})
                location = None
                if isinstance(location_data, dict):
                    location = str(location_data.get("name", ""))[:MAX_LOCATION_LEN] or None
                elif isinstance(location_data, str):
                    location = location_data[:MAX_LOCATION_LEN] or None

                # Description (HTML content, bounded)
                description = str(job_data.get("content", ""))[:MAX_DESCRIPTION_LEN] or None

                # Extract board token from candidate URL for company name
                board_token = self.extract_board_identifier(candidate.target_url) or "unknown"

                # Build bounded provider metadata
                departments = job_data.get("departments", [])
                provider_meta = {}
                if isinstance(departments, list) and departments:
                    dept_names = [
                        str(d.get("name", ""))[:128]
                        for d in departments[:10]
                        if isinstance(d, dict)
                    ]
                    provider_meta["departments"] = dept_names

                updated_at = job_data.get("updated_at")
                if updated_at:
                    provider_meta["updated_at"] = str(updated_at)[:64]

                raw_job = RawJob(
                    provenance=DiscoveryProvenanceDTO(
                        strategy_id=self.strategy_id,
                        adapter_id=self.strategy_id,
                        source_id=candidate.source_id,
                        source_type="direct_ats",
                        source_url=candidate.target_url,
                        source_job_id=job_id,
                        apply_url=apply_url,
                        provider_name=self.ats_name,
                    ),
                    title=title,
                    company=board_token[:MAX_COMPANY_LEN],
                    location=location,
                    description=description,
                    provider_metadata=provider_meta if provider_meta else None,
                )
                raw_jobs.append(raw_job)

            except Exception as e:
                # One malformed job entry must not crash the entire extraction
                logger.warning(f"Greenhouse: skipping malformed job entry: {e}")
                continue

        return raw_jobs

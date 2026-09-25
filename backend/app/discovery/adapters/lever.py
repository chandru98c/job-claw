import json
import re
import time
import logging
from typing import Optional
import urllib.parse

from app.discovery.interfaces import ATSAdapter
from app.schemas.discovery import (
    StrategyCandidate,
    StrategyExecutionResult,
    RawJob,
    DiscoveryProvenanceDTO,
    DiscoveryError,
    DiscoveryErrorType,
    SourceConfig,
)
from app.core.http import SafeHTTPClient

logger = logging.getLogger(__name__)

# Pattern 1: jobs.lever.co/{token} or api.lever.co/v0/postings/{token}
_LEVER_BOARD_PATTERN = re.compile(
    r"^https?://(?:jobs\.lever\.co|api\.lever\.co/v0/postings)/([a-zA-Z0-9_-]+)(?:/.*|\?.*)?$",
    re.IGNORECASE,
)

class LeverAdapter(ATSAdapter):
    """
    ATS adapter for Lever job boards.
    """

    @property
    def strategy_id(self) -> str:
        return "lever_ats"

    @property
    def name(self) -> str:
        return "Lever ATS Adapter"

    @property
    def ats_name(self) -> str:
        return "Lever"

    @property
    def priority(self) -> int:
        return 10

    @property
    def capabilities(self) -> dict:
        return {
            "supports_pagination": False,
            "supports_json_api": True,
        }

    def extract_board_identifier(self, url: str) -> Optional[str]:
        match = _LEVER_BOARD_PATTERN.match(url)
        if match:
            return match.group(1)
        return None

    def recognizes_url(self, url: str) -> bool:
        return self.extract_board_identifier(url) is not None

    def generate_candidates(self, url: str = None, source: SourceConfig = None) -> list[StrategyCandidate]:
        source_id = None
        if source:
            source_id = source.source_id
            
        if source and source.identifier:
            board_token = source.identifier
        elif url:
            board_token = self.extract_board_identifier(url)
        else:
            return []
            
        if not board_token:
            return []

        # Construct the API URL for lever
        api_url = f"https://api.lever.co/v0/postings/{board_token}?mode=json"

        return [
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=api_url,
                evidence=f"Lever board token: {board_token}",
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
        start_time = time.monotonic()
        result = StrategyExecutionResult(
            strategy_id=self.strategy_id,
            adapter_id=self.strategy_id,
            candidate_id=candidate.candidate_id,
        )

        try:
            url = candidate.validated_url or candidate.target_url
            response_data = await http_client.get(url)
            result.requests_attempted = 1
            
            # For Lever, sometimes the API returns a 404 or 403.
            # SafeHTTPClient raises an exception for non-2xx status, so we would catch it below.
            # If the response data doesn't look like JSON, we could trigger fallback.
            try:
                # Just test if it's JSON
                json.loads(response_data.decode("utf-8"))
            except ValueError:
                # Need browser fallback if not JSON
                raise ValueError("Response is not JSON, requires browser fallback")

            raw_jobs = await self.extract_jobs(response_data, candidate)
            result.raw_jobs = raw_jobs
            result.jobs_discovered = len(raw_jobs)

        except Exception as e:
            logger.error(f"Lever adapter failed for {candidate.candidate_id}: {e}")
            result.success = False
            result.requests_attempted = 1
            
            # Force browser fallback if the API is hidden/fails
            error_type = DiscoveryErrorType.NETWORK_FAILURE
            if "browser fallback" in str(e).lower() or "403" in str(e) or "404" in str(e):
                error_type = DiscoveryErrorType.REQUIRES_BROWSER_FALLBACK
            elif "parse" in str(e).lower() or "json" in str(e).lower():
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
        try:
            # Handle both direct API response (List) and potential browser fallback responses
            content_str = response_data.decode("utf-8")
            
            jobs = []
            
            # If browser fallback HTML
            if "window.leverJobsOptions" in content_str:
                # Extremely naive extraction from HTML script block
                match = re.search(r"window\.leverJobsOptions\s*=\s*({.*?});", content_str, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    jobs = data.get("postings", [])
            else:
                jobs = json.loads(content_str)

            if not isinstance(jobs, list):
                return []

            raw_jobs = []
            board_id = self.extract_board_identifier(candidate.target_url) or "unknown"

            for j in jobs:
                title = j.get("text", "")
                if not title:
                    continue

                categories = j.get("categories", {})
                location = categories.get("location", "")
                
                # Check for location in direct properties too
                if not location and "country" in j:
                    location = j.get("country", "")

                apply_url = j.get("hostedUrl", "") or j.get("applyUrl", "")
                job_id = str(j.get("id", ""))
                
                if not job_id:
                    continue
                    
                description = j.get("descriptionPlain", "") or j.get("description", "")
                employment_type = categories.get("commitment", "")
                
                remote_status = None
                workplace = j.get("workplaceType", "")
                if workplace and workplace.lower() == "remote":
                    remote_status = "Remote"
                elif location and "remote" in location.lower():
                    remote_status = "Remote"
                
                provider_metadata = {
                    "department": categories.get("department", "") or categories.get("team", ""),
                    "workplaceType": workplace,
                    "allLocations": categories.get("allLocations", []),
                    "lists": j.get("lists", [])
                }

                raw_jobs.append(
                    RawJob(
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
                        title=title[:255],
                        company=board_id[:255],
                        location=location[:255] if location else None,
                        description=description[:50000] if description else None,
                        employment_type=employment_type[:128] if employment_type else None,
                        remote_status=remote_status[:64] if remote_status else None,
                        provider_metadata=provider_metadata
                    )
                )
            return raw_jobs
        except Exception as e:
            logger.warning(f"Lever extraction error: {e}")
            return []

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
)
from app.core.http import SafeHTTPClient

logger = logging.getLogger(__name__)

# Pattern: apply.workable.com/{token}
_WORKABLE_BOARD_PATTERN = re.compile(
    r"^https?://(?:apply\.)?workable\.com/([a-zA-Z0-9_-]+)(?:/.*)?$",
    re.IGNORECASE,
)

class WorkableAdapter(ATSAdapter):
    @property
    def strategy_id(self) -> str:
        return "workable_ats"

    @property
    def name(self) -> str:
        return "Workable ATS Adapter"

    @property
    def ats_name(self) -> str:
        return "Workable"

    @property
    def priority(self) -> int:
        return 10

    def extract_board_identifier(self, url: str) -> Optional[str]:
        match = _WORKABLE_BOARD_PATTERN.match(url)
        if match:
            token = match.group(1).lower()
            if token not in ["j", "api"]: # ignore API or job detail routes
                return token
        return None

    def recognizes_url(self, url: str) -> bool:
        return self.extract_board_identifier(url) is not None

    def generate_candidates(self, url: str) -> list[StrategyCandidate]:
        board_token = self.extract_board_identifier(url)
        if not board_token:
            return []

        # Construct the API URL for Workable
        # Workable public API for career pages:
        api_url = f"https://apply.workable.com/api/v3/accounts/{board_token}/jobs"

        return [
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=api_url,
                evidence=f"Workable board token: {board_token}",
                confidence=0.95,
                source="url_pattern_match",
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
            
            try:
                json.loads(response_data.decode("utf-8"))
            except ValueError:
                raise ValueError("Response is not JSON, requires browser fallback")

            raw_jobs = await self.extract_jobs(response_data, candidate)
            result.raw_jobs = raw_jobs
            result.jobs_discovered = len(raw_jobs)

        except Exception as e:
            logger.error(f"Workable adapter failed for {candidate.candidate_id}: {e}")
            result.success = False
            result.requests_attempted = 1
            
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
            content_str = response_data.decode("utf-8")
            data = json.loads(content_str)
            jobs = data.get("results", [])

            if not isinstance(jobs, list):
                return []

            raw_jobs = []
            board_id = self.extract_board_identifier(candidate.target_url) or "unknown"

            for j in jobs:
                title = j.get("title", "")
                if not title:
                    continue

                location_obj = j.get("location", {})
                location = location_obj.get("city", "") or location_obj.get("country", "")

                apply_url = f"https://apply.workable.com/{board_id}/j/{j.get('shortcode')}"

                raw_jobs.append(
                    RawJob(
                        provenance=DiscoveryProvenanceDTO(
                            strategy_id=self.strategy_id,
                            adapter_id=self.strategy_id,
                            source_type="direct_ats",
                            source_url=candidate.target_url,
                            source_job_id=str(j.get("id", "") or j.get("shortcode", "")),
                            apply_url=apply_url,
                            provider_name=self.ats_name,
                        ),
                        title=title[:255],
                        company=board_id,
                        location=location[:255] if location else None,
                        description=None,
                    )
                )
            return raw_jobs
        except Exception as e:
            logger.warning(f"Workable extraction error: {e}")
            return []

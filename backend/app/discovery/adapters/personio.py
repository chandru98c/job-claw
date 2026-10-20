from __future__ import annotations

import json
import re
import time
import logging
from typing import Optional

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

# Matches: {slug}.jobs.personio.com or {slug}.jobs.personio.de
_PERSONIO_URL_PATTERN = re.compile(
    r"^(?:https?://)?([a-zA-Z0-9_-]+)\.jobs\.personio\.(?:com|de)(?:/.*)?$",
    re.IGNORECASE,
)


class PersonioAdapter(ATSAdapter):
    @property
    def strategy_id(self) -> str:
        return "personio_ats"

    @property
    def name(self) -> str:
        return "Personio ATS Adapter"

    @property
    def ats_name(self) -> str:
        return "Personio"

    @property
    def priority(self) -> int:
        return 10

    def extract_board_identifier(self, url: str) -> Optional[str]:
        if not url:
            return None
        match = _PERSONIO_URL_PATTERN.match(url.strip())
        if match:
            return match.group(1).lower()
        return None

    def recognizes_url(self, url: str) -> bool:
        return self.extract_board_identifier(url) is not None

    def generate_candidates(self, url: str = None, source: SourceConfig = None) -> list[StrategyCandidate]:
        source_id = source.source_id if source else None
        board_token = self.resolve_board_identifier(url, source)
        if not board_token:
            return []

        # Personio public search.json endpoint
        target_url = f"https://{board_token}.jobs.personio.com/search.json"
        return [
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=target_url,
                evidence=f"Personio board: {board_token}",
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
            response_data = await http_client.get(
                url,
                headers={"Accept": "application/json", "User-Agent": "JobClaw/1.0 (Direct ATS Discovery)"},
            )
            result.requests_attempted = 1

            raw_jobs = await self.extract_jobs(response_data, candidate)
            result.raw_jobs = raw_jobs
            result.jobs_discovered = len(raw_jobs)
            result.success = True

        except Exception as e:
            logger.warning(f"Personio adapter failed for {candidate.target_url}: {e}")
            result.success = False
            result.requests_attempted = 1
            result.errors.append(
                DiscoveryError(
                    error_type=DiscoveryErrorType.HTTP_STATUS_ERROR,
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
            text = response_data.decode("utf-8", errors="replace")
            data = json.loads(text)
        except Exception as e:
            logger.error(f"Failed to parse Personio JSON: {e}")
            return []

        jobs: list[RawJob] = []
        if not isinstance(data, list):
            return []

        # Extract board identifier from target URL
        match = re.search(r"https?://([a-zA-Z0-9_-]+)\.jobs\.personio\.", candidate.target_url)
        board_token = match.group(1) if match else "unknown"

        for item in data:
            if not isinstance(item, dict):
                continue

            job_id = str(item.get("id", ""))
            title = (item.get("name") or "").strip()
            if not title:
                continue

            # Determine job URL
            job_url = f"https://{board_token}.jobs.personio.com/job/{job_id}"

            # Location formatting
            offices = item.get("offices") or []
            office = item.get("office") or ""
            if offices and isinstance(offices, list):
                location_str = ", ".join(offices)
            else:
                location_str = office
            if len(location_str) > 500:
                location_str = location_str[:497] + "..."

            # Department & company
            department = item.get("department") or item.get("category") or ""
            company = item.get("subcompany") or board_token

            # Employment schedule
            schedule = item.get("schedule") or item.get("employment_type") or "full-time"

            # Keywords & description
            keywords = item.get("keywords") or ""
            desc = item.get("description") or ""
            full_description = f"{title}\n\nDepartment: {department}\nLocation: {location_str}\nSchedule: {schedule}\nKeywords: {keywords}\n\n{desc}"

            # Remote detection
            is_remote = False
            loc_lower = f"{location_str} {keywords}".lower()
            if any(term in loc_lower for term in ["remote", "hybrid", "telecommute", "anywhere", "wfh"]):
                is_remote = True

            provenance = DiscoveryProvenanceDTO(
                source_id=candidate.source_id,
                strategy_id=self.strategy_id,
                source_type="direct_ats",
                source_url=candidate.target_url,
                source_job_id=job_id,
                apply_url=job_url,
                confidence_score=candidate.confidence,
                ats_platform=self.ats_name,
                job_board_token=board_token,
            )

            job = RawJob(
                provenance=provenance,
                title=title[:512],
                company=company[:256],
                location=location_str[:512] if location_str else "India",
                description=full_description[:50000],
                employment_type=schedule[:128] if schedule else "full-time",
                remote_status="remote" if is_remote else "on-site",
                url=job_url,
                apply_url=job_url,
                provider_metadata={"department": department, "job_id": job_id}
            )
            jobs.append(job)

        return jobs

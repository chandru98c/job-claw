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

# Matches: {slug}.breezy.hr
_BREEZY_URL_PATTERN = re.compile(
    r"^(?:https?://)?([a-zA-Z0-9_-]+)\.breezy\.hr(?:/.*)?$",
    re.IGNORECASE,
)


class BreezyAdapter(ATSAdapter):
    @property
    def strategy_id(self) -> str:
        return "breezy_ats"

    @property
    def name(self) -> str:
        return "Breezy HR ATS Adapter"

    @property
    def ats_name(self) -> str:
        return "Breezy HR"

    @property
    def priority(self) -> int:
        return 10

    def extract_board_identifier(self, url: str) -> Optional[str]:
        if not url:
            return None
        match = _BREEZY_URL_PATTERN.match(url.strip())
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

        # Breezy HR public JSON endpoint
        target_url = f"https://{board_token}.breezy.hr/json"
        return [
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=target_url,
                evidence=f"Breezy board: {board_token}",
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
            logger.warning(f"Breezy adapter failed for {candidate.target_url}: {e}")
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
            data = json.loads(response_data.decode("utf-8"))
        except Exception as e:
            logger.error(f"Failed to parse Breezy JSON: {e}")
            return []

        if not isinstance(data, list):
            return []

        jobs: list[RawJob] = []
        company_fallback = candidate.evidence.replace("Breezy board: ", "")

        for item in data:
            if not isinstance(item, dict):
                continue

            job_id = str(item.get("id") or item.get("_id") or "")
            title = item.get("name") or item.get("title") or ""
            title = title.strip()
            if not title or not job_id:
                continue

            # Apply URL
            apply_url = item.get("url")
            if not apply_url:
                friendly = item.get("friendly_id") or job_id
                board = candidate.evidence.replace("Breezy board: ", "")
                apply_url = f"https://{board}.breezy.hr/p/{job_id}-{friendly}"

            # Location formatting
            loc_dict = item.get("location") or {}
            if isinstance(loc_dict, dict):
                city = str(loc_dict.get("city") or "")
                state_data = loc_dict.get("state")
                state = state_data.get("name") if isinstance(state_data, dict) else str(state_data or "")
                country_data = loc_dict.get("country")
                country_name = country_data.get("name") if isinstance(country_data, dict) else str(country_data or "")
                parts = [p for p in [city, state, country_name] if p]
                loc_str = ", ".join(parts) if parts else str(loc_dict.get("name") or "")
                is_remote = bool(loc_dict.get("is_remote", False))
            else:
                loc_str = str(loc_dict) if loc_dict else None
                is_remote = False

            remote_status = "remote" if is_remote else "on-site"

            # Job Type
            type_data = item.get("type")
            job_type = type_data.get("name") if isinstance(type_data, dict) else (type_data or "Full-Time")

            # Department / metadata
            dept = str(item.get("department") or "")
            desc = f"Position: {title}\nDepartment: {dept}\nLocation: {loc_str or 'Unspecified'}"

            provenance = DiscoveryProvenanceDTO(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                source_id=candidate.source_id,
                source_type="direct_ats",
                source_url=candidate.target_url,
                source_job_id=job_id,
                apply_url=apply_url,
                provider_name=self.ats_name,
            )

            raw_job = RawJob(
                provenance=provenance,
                title=title[:255],
                company=company_fallback[:255],
                description=desc[:50000],
                location=loc_str[:255] if loc_str else None,
                remote_status=remote_status[:64],
                employment_type=str(job_type)[:128],
                provider_metadata={"department": dept}
            )
            jobs.append(raw_job)

        return jobs

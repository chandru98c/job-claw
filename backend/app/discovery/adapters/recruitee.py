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

# Matches: {slug}.recruitee.com or careers.{custom_domain}
_RECRUITEE_URL_PATTERN = re.compile(
    r"^(?:https?://)?([a-zA-Z0-9_-]+)\.recruitee\.com(?:/.*)?$",
    re.IGNORECASE,
)


class RecruiteeAdapter(ATSAdapter):
    @property
    def strategy_id(self) -> str:
        return "recruitee_ats"

    @property
    def name(self) -> str:
        return "Recruitee ATS Adapter"

    @property
    def ats_name(self) -> str:
        return "Recruitee"

    @property
    def priority(self) -> int:
        return 10

    def extract_board_identifier(self, url: str) -> Optional[str]:
        if not url:
            return None
        match = _RECRUITEE_URL_PATTERN.match(url.strip())
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

        # Recruitee provides a public JSON offers API
        target_url = f"https://{board_token}.recruitee.com/api/offers/"
        return [
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=target_url,
                evidence=f"Recruitee board: {board_token}",
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
            logger.warning(f"Recruitee adapter failed for {candidate.target_url}: {e}")
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
            logger.error(f"Failed to parse Recruitee JSON: {e}")
            return []

        offers = data.get("offers", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        jobs: list[RawJob] = []

        for offer in offers:
            if not isinstance(offer, dict):
                continue

            job_id = str(offer.get("id", ""))
            title = offer.get("title", "").strip()
            if not title or not job_id:
                continue

            # Build canonical apply URL
            apply_url = offer.get("careers_url") or offer.get("url")
            if not apply_url:
                slug_match = _RECRUITEE_URL_PATTERN.match(candidate.target_url)
                board = slug_match.group(1) if slug_match else "board"
                apply_url = f"https://{board}.recruitee.com/o/{job_id}"

            # Location formatting
            city = offer.get("city") or ""
            country = offer.get("country") or ""
            loc_str = offer.get("location") or f"{city}, {country}".strip(", ") or None

            # Remote status
            remote_val = "remote" if offer.get("remote") else "on-site"

            # Combine description and requirements
            desc_html = offer.get("description") or ""
            req_html = offer.get("requirements") or ""
            full_desc = f"{desc_html}\n{req_html}".strip() or title
            company_name = offer.get("company_name") or candidate.evidence.replace("Recruitee board: ", "")

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
                company=company_name[:255],
                description=full_desc[:50000],
                location=loc_str[:255] if loc_str else None,
                remote_status=remote_val[:64],
                employment_type=str(offer.get("employment_type_code") or "Full-time")[:128],
                provider_metadata={"department": offer.get("department") or ""}
            )
            jobs.append(raw_job)

        return jobs

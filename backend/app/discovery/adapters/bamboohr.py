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

# Matches: {slug}.bamboohr.com or {slug}.bamboohr.co.uk
_BAMBOOHR_URL_PATTERN = re.compile(
    r"^(?:https?://)?([a-zA-Z0-9_-]+)\.bamboohr\.(?:com|co\.uk)(?:/.*)?$",
    re.IGNORECASE,
)


class BambooHRAdapter(ATSAdapter):
    @property
    def strategy_id(self) -> str:
        return "bamboohr_ats"

    @property
    def name(self) -> str:
        return "BambooHR ATS Adapter"

    @property
    def ats_name(self) -> str:
        return "BambooHR"

    @property
    def priority(self) -> int:
        return 10

    def extract_board_identifier(self, url: str) -> Optional[str]:
        if not url:
            return None
        match = _BAMBOOHR_URL_PATTERN.match(url.strip())
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

        # BambooHR public careers embed2 endpoint (serves JSON of open jobs)
        target_url = f"https://{board_token}.bamboohr.com/jobs/embed2.php"
        return [
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=target_url,
                evidence=f"BambooHR board: {board_token}",
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
                headers={"Accept": "application/json, text/html", "User-Agent": "JobClaw/1.0 (Direct ATS Discovery)"},
            )
            result.requests_attempted = 1

            raw_jobs = await self.extract_jobs(response_data, candidate)
            result.raw_jobs = raw_jobs
            result.jobs_discovered = len(raw_jobs)
            result.success = True

        except Exception as e:
            logger.warning(f"BambooHR adapter failed for {candidate.target_url}: {e}")
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
        text = response_data.decode("utf-8", errors="replace")
        
        # Extract board identifier from target URL
        match = re.search(r"https?://([a-zA-Z0-9_-]+)\.bamboohr\.", candidate.target_url)
        board_token = match.group(1) if match else "unknown"

        # Check for empty response or redirect to generic BambooHR landing page
        if not text or not text.strip() or "The Complete HR Software" in text or "<title>BambooHR" in text:
            raise ValueError(f"BambooHR board '{board_token}' is inactive or redirected to homepage")

        jobs: list[RawJob] = []

        # Attempt 1: Parse as JSON (standard modern response)
        try:
            data = json.loads(text)
            if isinstance(data, dict) and ("departments" in data or "positions" in data or "labels" in data):
                for dept in data.get("departments", []):
                    dept_label = dept.get("label", "")
                    for pos in dept.get("positions", []):
                        job_id = str(pos.get("id", ""))
                        title = (pos.get("name") or "").strip()
                        if not title:
                            continue

                        job_url = pos.get("url") or f"https://{board_token}.bamboohr.com/careers/{job_id}"
                        loc_val = pos.get("location") or ""
                        if isinstance(loc_val, dict):
                            loc_parts = [loc_val.get("city"), loc_val.get("state"), loc_val.get("country")]
                            location_str = ", ".join([p for p in loc_parts if p])
                        else:
                            location_str = str(loc_val)
                        if len(location_str) > 500:
                            location_str = location_str[:497] + "..."

                        is_remote = False
                        if "remote" in location_str.lower() or "hybrid" in location_str.lower():
                            is_remote = True

                        full_desc = f"{title}\nDepartment: {dept_label}\nLocation: {location_str}\n\nJob details available at: {job_url}"

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
                            company=board_token[:256],
                            location=location_str[:512] if location_str else "India",
                            description=full_desc[:50000],
                            employment_type="full-time",
                            remote_status="remote" if is_remote else "on-site",
                            url=job_url,
                            apply_url=job_url,
                            provider_metadata={"department": dept_label, "job_id": job_id}
                        )
                        jobs.append(job)

                # Return valid parsed JSON result (even if 0 positions)
                return jobs
        except json.JSONDecodeError:
            pass

        # Attempt 2: HTML widget fallback via regex
        pos_regex = re.compile(
            r'<li[^>]*id=["\']bhrPositionID_(\d+)["\'][^>]*>.*?<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>(?:.*?<span[^>]*class=["\'][^"\']*BambooHR-ATS-Location[^"\']*["\'][^>]*>(.*?)</span>)?',
            re.DOTALL | re.IGNORECASE,
        )
        for m in pos_regex.finditer(text):
            job_id, raw_url, raw_title, raw_loc = m.groups()
            clean_title = re.sub(r"<[^>]+>", "", raw_title).strip()
            clean_loc = re.sub(r"<[^>]+>", "", raw_loc or "").strip()
            
            clean_url = raw_url.strip()
            if clean_url.startswith("//"):
                clean_url = "https:" + clean_url

            provenance = DiscoveryProvenanceDTO(
                source_id=candidate.source_id,
                strategy_id=self.strategy_id,
                source_type="direct_ats",
                source_url=candidate.target_url,
                source_job_id=job_id,
                apply_url=clean_url,
                confidence_score=candidate.confidence,
                ats_platform=self.ats_name,
                job_board_token=board_token,
            )

            job = RawJob(
                provenance=provenance,
                title=clean_title[:512],
                company=board_token[:256],
                location=clean_loc[:512] if clean_loc else "India",
                description=f"{clean_title}\nLocation: {clean_loc}\nURL: {clean_url}"[:50000],
                employment_type="full-time",
                remote_status="remote" if "remote" in clean_loc.lower() else "on-site",
                url=clean_url,
                apply_url=clean_url,
                provider_metadata={"job_id": job_id}
            )
            jobs.append(job)

        if jobs:
            return jobs

        # If not JSON and not HTML widget match, board is not active
        raise ValueError(f"BambooHR board '{board_token}' returned non-matching content")

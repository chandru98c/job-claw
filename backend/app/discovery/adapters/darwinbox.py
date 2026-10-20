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

# Matches: {tenant}.darwinbox.in or {tenant}.darwinbox.com
_DARWINBOX_URL_PATTERN = re.compile(
    r"^https?://([a-zA-Z0-9_-]+)\.darwinbox\.(in|com)(?:/.*)?$",
    re.IGNORECASE,
)


class DarwinboxAdapter(ATSAdapter):
    @property
    def strategy_id(self) -> str:
        return "darwinbox_ats"

    @property
    def name(self) -> str:
        return "Darwinbox ATS Adapter"

    @property
    def ats_name(self) -> str:
        return "Darwinbox"

    @property
    def priority(self) -> int:
        return 10

    def extract_board_identifier(self, url: str) -> Optional[str]:
        match = _DARWINBOX_URL_PATTERN.match(url)
        if match:
            tenant = match.group(1).lower()
            tld = match.group(2).lower()
            return f"{tenant}.darwinbox.{tld}"
        return None

    def recognizes_url(self, url: str) -> bool:
        return "darwinbox." in url.lower()

    def generate_candidates(self, url: str = None, source: SourceConfig = None) -> list[StrategyCandidate]:
        source_id = source.source_id if source else None
        board_token = None

        if source and source.identifier:
            board_token = source.identifier
        elif url:
            board_token = self.extract_board_identifier(url)

        if not board_token:
            return []

        if ".darwinbox." in board_token:
            base_host = board_token
        else:
            base_host = f"{board_token}.darwinbox.in"

        target_url = f"https://{base_host}/ms/candidateapi/job/alljobs"
        return [
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=target_url,
                evidence=f"Darwinbox tenant: {base_host}",
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
            match = re.search(r"https?://([a-zA-Z0-9_-]+)\.darwinbox\.(in|com)", url)
            tenant = match.group(1) if match else "unknown"
            tld = match.group(2) if match else "in"
            base_url = f"https://{tenant}.darwinbox.{tld}"

            headers = {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": base_url,
                "Referer": f"{base_url}/ms/candidatev2/main/careers/allJobs",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            }

            payload = {
                "companyId": "main",
                "page": 1,
                "sort_option": "new",
                "limit": 30,
            }

            # POST request via http_client
            # Note: SafeHTTPClient may only expose .get(), let's check or use internal httpx client
            if hasattr(http_client, "post"):
                resp_bytes = await http_client.post(url, headers=headers, json=payload)
            else:
                resp = await http_client.client.post(url, headers=headers, json=payload, params={"companyId": "main"})
                resp_bytes = resp.content

            result.requests_attempted = 1
            raw_jobs = await self.extract_jobs(resp_bytes, candidate)
            result.raw_jobs = raw_jobs
            result.jobs_discovered = len(raw_jobs)
            result.success = True

        except Exception as e:
            logger.warning(f"Darwinbox adapter failed for {candidate.target_url}: {e}")
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
        match = re.search(r"https?://([a-zA-Z0-9_-]+)\.darwinbox\.(in|com)", candidate.target_url)
        tenant = match.group(1) if match else "unknown"
        tld = match.group(2) if match else "in"
        base_url = f"https://{tenant}.darwinbox.{tld}"

        try:
            data = json.loads(response_data.decode("utf-8", errors="replace"))
        except Exception:
            return []

        jobs_list = data.get("data")
        if not isinstance(jobs_list, list):
            return []

        jobs: list[RawJob] = []
        for item in jobs_list:
            if not isinstance(item, dict):
                continue

            job_id = str(item.get("id") or item.get("_id") or "").strip()
            title = (
                item.get("designation_display_name")
                or item.get("title")
                or item.get("designation_name")
                or ""
            ).strip()

            if not job_id or not title:
                continue

            # Locations: city, state, country
            city = item.get("city") or item.get("job_location") or ""
            state = item.get("state") or ""
            country = item.get("country") or "India"
            loc_parts = [p for p in [city, state, country] if p]
            location_str = ", ".join(loc_parts) if loc_parts else "Chennai / South India"
            if len(location_str) > 500:
                location_str = location_str[:497] + "..."

            is_remote = bool(item.get("is_remote") or 0)
            emp_type = item.get("emp_type_name") or item.get("emp_type") or "full-time"
            dept = item.get("department_name") or item.get("functional_area_name") or ""
            desc = item.get("job_description") or item.get("description") or ""

            job_url = f"{base_url}/ms/candidate/careers/{job_id}"
            full_desc = f"{title}\nDepartment: {dept}\nLocation: {location_str}\n\n{desc}"

            provenance = DiscoveryProvenanceDTO(
                source_id=candidate.source_id,
                strategy_id=self.strategy_id,
                source_type="direct_ats",
                source_url=candidate.target_url,
                source_job_id=job_id,
                apply_url=job_url,
                confidence_score=candidate.confidence,
                ats_platform=self.ats_name,
                job_board_token=tenant,
            )

            job = RawJob(
                provenance=provenance,
                title=title[:512],
                company=tenant.title()[:256],
                location=location_str[:512] if location_str else "India",
                description=full_desc[:50000],
                employment_type=emp_type[:128] if emp_type else "full-time",
                remote_status="remote" if is_remote else "on-site",
                url=job_url,
                apply_url=job_url,
                provider_metadata={"department": dept, "job_id": job_id}
            )
            jobs.append(job)

        return jobs

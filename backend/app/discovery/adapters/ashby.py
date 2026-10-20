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

# Pattern: jobs.ashbyhq.com/{token} or {token}.ashbyhq.com
_ASHBY_BOARD_PATTERN = re.compile(
    r"^(?:https?://)?(?:jobs\.ashbyhq\.com/([a-zA-Z0-9_-]+)|([a-zA-Z0-9_-]+)\.ashbyhq\.com)(?:/.*)?$",
    re.IGNORECASE,
)


class AshbyAdapter(ATSAdapter):
    @property
    def strategy_id(self) -> str:
        return "ashby_ats"

    @property
    def name(self) -> str:
        return "Ashby ATS Adapter"

    @property
    def ats_name(self) -> str:
        return "Ashby"

    @property
    def priority(self) -> int:
        return 10

    def extract_board_identifier(self, url: str) -> Optional[str]:
        if not url:
            return None
        match = _ASHBY_BOARD_PATTERN.match(url.strip())
        if match:
            token = (match.group(1) or match.group(2)).lower()
            if token not in ["jobs", "api", "www"]:
                return token
        return None

    def recognizes_url(self, url: str) -> bool:
        return self.extract_board_identifier(url) is not None

    def generate_candidates(self, url: str = None, source: SourceConfig = None) -> list[StrategyCandidate]:
        source_id = source.source_id if source else None
        board_token = self.resolve_board_identifier(url, source)
        if not board_token:
            return []

        # Target the official Ashby public posting API (no browser needed, fast JSON)
        target_url = f"https://api.ashbyhq.com/posting-api/job-board/{board_token}?includeCompensation=true"
        return [
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=target_url,
                evidence=f"Ashby board token: {board_token}",
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
            logger.info(f"Ashby API fetch failed: {e}")
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
            content_str = response_data.decode("utf-8")
            board_id = (candidate.evidence or "").replace("Ashby board token: ", "").strip()
            if not board_id:
                board_id = self.extract_board_identifier(candidate.target_url) or "unknown"
            jobs_list = []

            # 1. Try Direct JSON API format
            try:
                data = json.loads(content_str)
                if isinstance(data, dict) and "jobs" in data:
                    jobs_list = data["jobs"]
            except Exception:
                pass

            # 2. Fallback to __NEXT_DATA__ if HTML was returned
            if not jobs_list:
                match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', content_str, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    page_props = data.get("props", {}).get("pageProps", {})
                    job_board = page_props.get("jobBoard", {})
                    jobs_list = job_board.get("jobPostings", [])

            if not jobs_list:
                return []

            raw_jobs: list[RawJob] = []

            for j in jobs_list:
                if not isinstance(j, dict):
                    continue

                title = (j.get("title") or "").strip()
                job_id = str(j.get("id") or "")
                if not title or not job_id:
                    continue

                location = j.get("locationName") or j.get("location") or ""
                apply_url = j.get("jobPageUrl") or j.get("jobUrl") or f"https://jobs.ashbyhq.com/{board_id}/{job_id}"
                description = j.get("descriptionHtml") or j.get("descriptionPlain") or title
                employment_type = j.get("employmentType") or "Full-time"
                is_remote = bool(j.get("isRemote"))
                remote_status = "remote" if is_remote else "on-site"

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

                raw_jobs.append(
                    RawJob(
                        provenance=provenance,
                        title=title[:255],
                        company=board_id[:255],
                        description=description[:50000],
                        location=location[:255] if location else None,
                        remote_status=remote_status[:64],
                        employment_type=employment_type[:128],
                        provider_metadata={"department": j.get("departmentName") or ""}
                    )
                )

            return raw_jobs

        except Exception as e:
            logger.error(f"Error extracting Ashby jobs: {e}")
            return []

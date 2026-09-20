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

# Pattern: jobs.ashbyhq.com/{token}
_ASHBY_BOARD_PATTERN = re.compile(
    r"^https?://jobs\.ashbyhq\.com/([a-zA-Z0-9_-]+)(?:/.*)?$",
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
        match = _ASHBY_BOARD_PATTERN.match(url)
        if match:
            return match.group(1)
        return None

    def recognizes_url(self, url: str) -> bool:
        return self.extract_board_identifier(url) is not None

    def generate_candidates(self, url: str = None, source: SourceConfig = None) -> list[StrategyCandidate]:
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

        # We probe the career page itself. Ashby is an SPA, so it usually requires JS.
        target_url = f"https://jobs.ashbyhq.com/{board_token}"
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
            response_data = await http_client.get(url)
            result.requests_attempted = 1
            
            # Since Ashby is dynamic, check if we got the raw HTML shell
            content_str = response_data.decode("utf-8")
            if "Next.js" in content_str or "ashby" in content_str.lower():
                # We can try to parse __NEXT_DATA__ here, but if not found or parsing fails, we fallback to Browser.
                if "__NEXT_DATA__" not in content_str:
                     raise ValueError("Requires Browser Fallback")
            
            raw_jobs = await self.extract_jobs(response_data, candidate)
            
            if not raw_jobs:
                 # If we extracted 0 jobs, maybe JS is required
                 raise ValueError("Requires Browser Fallback")
                 
            result.raw_jobs = raw_jobs
            result.jobs_discovered = len(raw_jobs)

        except Exception as e:
            logger.info(f"Ashby adapter requesting browser fallback: {e}")
            result.success = False
            result.requests_attempted = 1
            
            # For Ashby we almost always fall back to Browser due to dynamic rendering
            result.errors.append(
                DiscoveryError(
                    error_type=DiscoveryErrorType.REQUIRES_BROWSER_FALLBACK,
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
            jobs = []
            
            # 1. Try __NEXT_DATA__ JSON extraction (HTTP first success)
            match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', content_str, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                # Next.js props structure
                page_props = data.get("props", {}).get("pageProps", {})
                job_board = page_props.get("jobBoard", {})
                jobs = job_board.get("jobPostings", [])
            else:
                # 2. Browser fallback HTML structure
                # The browser fallback HTML content might just have the rendered DOM.
                # However, our BrowserAcquisition currently intercepts network candidates. 
                # Wait, if we use browser fallback, we just parse the DOM.
                # But DOM parsing is brittle. Ashby's browser fallback might observe the GraphQL API!
                pass

            if not jobs:
                return []

            raw_jobs = []
            board_id = self.extract_board_identifier(candidate.target_url) or "unknown"

            for j in jobs:
                title = j.get("title", "")
                if not title: continue

                location = j.get("locationName", "")
                apply_url = j.get("jobPageUrl", "")
                job_id = str(j.get("id", ""))
                
                if not job_id:
                    continue
                    
                if not apply_url:
                    apply_url = f"https://jobs.ashbyhq.com/{board_id}/{job_id}"

                description = j.get("descriptionHtml", "")
                employment_type = j.get("employmentType", "")
                remote_status = "Remote" if j.get("isRemote") else None
                
                provider_metadata = {
                    "department": j.get("departmentName", ""),
                    "secondaryLocations": j.get("secondaryLocations", []),
                    "compensationTier": j.get("compensationTier", {})
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
        except Exception:
            return []

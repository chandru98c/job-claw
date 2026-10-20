"""
Zoho Recruit ATS Adapter.

Zoho Recruit is the primary ATS used by Indian startups, SMEs, and tech companies
across Chennai, Bangalore, and Hyderabad.

API / Extraction Strategy:
  Zoho Recruit career sites (e.g. https://{tenant}.zohorecruit.in/jobs/Careers)
  embed the entire active openings list as an HTML-escaped JSON array inside a hidden
  <input id="jobs" value="..."> element.
  This allows single-fetch extraction of all company openings in ~200ms without
  headless browsers or bot blocks.
"""
from __future__ import annotations

import re
import html
import json
import time
import logging
import urllib.parse
from datetime import datetime, timezone
from typing import Optional, List
from bs4 import BeautifulSoup

from app.discovery.interfaces import ATSAdapter, StrategyCategory
from app.schemas.discovery import (
    StrategyCandidate,
    StrategyExecutionResult,
    RawJob,
    DiscoveryProvenanceDTO,
    DiscoveryError,
    DiscoveryErrorType,
    SourceConfig,
    MAX_TITLE_LEN,
    MAX_COMPANY_LEN,
    MAX_LOCATION_LEN,
)
from app.core.http import SafeHTTPClient

logger = logging.getLogger(__name__)

_ZOHO_PATTERN = re.compile(
    r"^(?:https?://)?[a-zA-Z0-9_\-\.]+\.zohorecruit\.(?:in|com|eu|com\.au|net)",
    re.IGNORECASE
)

class ZohoRecruitAdapter(ATSAdapter):
    """
    Adapter for Zoho Recruit ATS boards (*.zohorecruit.in / *.zohorecruit.com).
    """

    @property
    def strategy_id(self) -> str:
        return "zohorecruit_ats"

    @property
    def name(self) -> str:
        return "Zoho Recruit ATS Adapter"

    @property
    def ats_name(self) -> str:
        return "Zoho Recruit"

    @property
    def priority(self) -> int:
        return 10  # High priority direct ATS

    @property
    def category(self) -> StrategyCategory:
        return StrategyCategory.ATS_ADAPTER

    @property
    def capabilities(self) -> dict:
        return {
            "supports_pagination": False,
            "supports_json_api": True,
            "max_jobs_per_request": 500,
        }

    def extract_board_identifier(self, url: str) -> Optional[str]:
        """Extracts the tenant host (e.g. 'agnikul.zohorecruit.in')."""
        if not url:
            return None
        clean = url.strip()
        if not clean.startswith(("http://", "https://")):
            clean = f"https://{clean}"
        try:
            parsed = urllib.parse.urlparse(clean)
            netloc = parsed.netloc.lower()
            if "zohorecruit" in netloc:
                return netloc
        except Exception:
            pass
        return None

    def recognizes_url(self, url: str) -> bool:
        return bool(_ZOHO_PATTERN.match(url))

    def can_handle(self, source: SourceConfig) -> bool:
        if source.ats_type and source.ats_type.lower() in ("zohorecruit", "zoho"):
            return True
        if source.careers_url and self.recognizes_url(source.careers_url):
            return True
        if source.domain and "zohorecruit" in source.domain.lower():
            return True
        return False

    def generate_candidates(self, url: str = None, source: Optional[SourceConfig] = None) -> list[StrategyCandidate]:
        host = None
        if url:
            host = self.extract_board_identifier(url)
        if not host and source and source.careers_url:
            host = self.extract_board_identifier(source.careers_url)
        if not host and source and source.domain:
            host = self.extract_board_identifier(source.domain) or (source.domain if "zohorecruit" in source.domain.lower() else None)

        if not host:
            return []
        
        target_url = f"https://{host}/jobs/Careers"
        return [
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=target_url,
                evidence=f"Zoho Recruit careers host detected: {host}",
                confidence=0.95,
                source=source.domain if source else host,
                source_id=source.source_id if source else None,
                priority=self.priority,
            )
        ]

    async def extract_jobs(
        self,
        response_data: bytes,
        candidate: StrategyCandidate,
    ) -> list[RawJob]:
        host = self.extract_board_identifier(candidate.target_url) or candidate.source or "unknown"
        html_text = response_data.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html_text, "html.parser")
        
        input_tag = soup.find("input", id="jobs")
        if not input_tag or not input_tag.get("value"):
            return []

        raw_val = input_tag.get("value", "")
        unescaped = html.unescape(raw_val)
        openings = json.loads(unescaped)

        company_name = host.split(".")[0].replace("-", " ").title()
        if candidate.source:
            company_name = candidate.source.split(".")[0].replace("-", " ").title()

        raw_jobs: List[RawJob] = []
        for item in openings:
            if not isinstance(item, dict):
                continue

            job_id = str(item.get("id") or item.get("ID") or "")
            title = str(item.get("Posting_Title") or item.get("Job_Title") or item.get("title") or "").strip()
            if not title:
                continue

            city = item.get("City") or ""
            country = item.get("Country") or ""
            state = item.get("State") or ""
            loc_parts = [p for p in [city, state, country] if p]
            location_str = ", ".join(loc_parts) if loc_parts else "India"

            is_remote = bool(item.get("Remote_Job"))
            remote_status = "Remote" if is_remote else ("Hybrid" if "hybrid" in location_str.lower() else "On-site")

            apply_url = f"https://{host}/jobs/Careers/{job_id}"
            desc = item.get("Job_Description") or item.get("description") or f"{title} at {company_name} ({location_str})"

            provenance = DiscoveryProvenanceDTO(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                source_id=candidate.source_id,
                source_type="direct_ats",
                source_url=candidate.target_url,
                source_job_id=job_id,
                apply_url=apply_url,
                provider_name="Zoho Recruit",
                discovery_method=self.strategy_id,
                discovered_at=datetime.now(timezone.utc)
            )

            raw_jobs.append(RawJob(
                provenance=provenance,
                title=title[:MAX_TITLE_LEN],
                company=company_name[:MAX_COMPANY_LEN],
                location=location_str[:MAX_LOCATION_LEN],
                description=desc,
                employment_type=item.get("Job_Type") or "Full-time",
                remote_status=remote_status,
                provider_metadata={
                    "zoho_opening_id": job_id,
                    "raw_city": city,
                    "raw_country": country,
                    "remote_job": is_remote
                }
            ))

        return raw_jobs

    async def execute(self, candidate: StrategyCandidate, http_client: SafeHTTPClient) -> StrategyExecutionResult:
        host = self.extract_board_identifier(candidate.target_url)
        if not host:
            return StrategyExecutionResult(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                candidate_id=candidate.candidate_id,
                success=False,
                errors=[
                    DiscoveryError(
                        error_type=DiscoveryErrorType.ADAPTER_MISMATCH,
                        strategy_id=self.strategy_id,
                        adapter_id=self.strategy_id,
                        candidate_id=candidate.candidate_id,
                        message=f"Could not extract Zoho host from {candidate.target_url}"
                    )
                ]
            )

        fetch_url = f"https://{host}/jobs/Careers"
        start_time = time.monotonic()
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            content_bytes = await http_client.get(fetch_url, headers=headers)
            raw_jobs = await self.extract_jobs(content_bytes, candidate)

            logger.info(f"Zoho Recruit adapter found {len(raw_jobs)} jobs for {host}")
            return StrategyExecutionResult(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                candidate_id=candidate.candidate_id,
                success=True,
                jobs_discovered=len(raw_jobs),
                raw_jobs=raw_jobs,
                duration_seconds=time.monotonic() - start_time
            )

        except Exception as e:
            logger.error(f"Zoho Recruit extraction failed for {fetch_url}: {e}", exc_info=True)
            return StrategyExecutionResult(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                candidate_id=candidate.candidate_id,
                success=False,
                errors=[
                    DiscoveryError(
                        error_type=DiscoveryErrorType.PARSING_FAILURE,
                        strategy_id=self.strategy_id,
                        adapter_id=self.strategy_id,
                        candidate_id=candidate.candidate_id,
                        message=str(e)
                    )
                ],
                duration_seconds=time.monotonic() - start_time
            )

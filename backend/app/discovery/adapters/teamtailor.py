from __future__ import annotations

import re
import time
import logging
from typing import Optional
from xml.etree import ElementTree as ET

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

# Matches: {slug}.teamtailor.com
_TEAMTAILOR_URL_PATTERN = re.compile(
    r"^(?:https?://)?([a-zA-Z0-9_-]+)\.teamtailor\.com(?:/.*)?$",
    re.IGNORECASE,
)
_JOB_ID_RE = re.compile(r"/jobs/(\d+)")


class TeamtailorAdapter(ATSAdapter):
    @property
    def strategy_id(self) -> str:
        return "teamtailor_ats"

    @property
    def name(self) -> str:
        return "Teamtailor ATS Adapter"

    @property
    def ats_name(self) -> str:
        return "Teamtailor"

    @property
    def priority(self) -> int:
        return 10

    def extract_board_identifier(self, url: str) -> Optional[str]:
        if not url:
            return None
        match = _TEAMTAILOR_URL_PATTERN.match(url.strip())
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

        if not board_token:
            return []

        # Teamtailor public jobs.rss feed
        target_url = f"https://{board_token}.teamtailor.com/jobs.rss"
        return [
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=target_url,
                evidence=f"Teamtailor board: {board_token}",
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
                headers={"Accept": "application/rss+xml, text/xml, application/xml", "User-Agent": "JobClaw/1.0 (Direct ATS Discovery)"},
            )
            result.requests_attempted = 1

            raw_jobs = await self.extract_jobs(response_data, candidate)
            result.raw_jobs = raw_jobs
            result.jobs_discovered = len(raw_jobs)
            result.success = True

        except Exception as e:
            logger.warning(f"Teamtailor adapter failed for {candidate.target_url}: {e}")
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
            xml_text = response_data.decode("utf-8", errors="replace")
            root = ET.fromstring(xml_text)
        except Exception as e:
            logger.error(f"Failed to parse Teamtailor RSS XML: {e}")
            return []

        channel = root.find("channel")
        if channel is None:
            return []

        company_name = candidate.evidence.replace("Teamtailor board: ", "")
        channel_title = channel.findtext("title")
        if channel_title:
            company_name = channel_title.replace("Careers", "").replace("Jobs", "").strip() or company_name

        namespaces = {"tt": "https://teamtailor.com/locations"}
        jobs: list[RawJob] = []

        for item in channel.findall("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or link).strip()
            if not title or not link:
                continue

            id_match = _JOB_ID_RE.search(guid) or _JOB_ID_RE.search(link)
            job_id = id_match.group(1) if id_match else guid

            # Extract location from tt:city, tt:country
            city = item.findtext("tt:city", namespaces=namespaces) or ""
            country = item.findtext("tt:country", namespaces=namespaces) or ""
            loc_parts = [p for p in [city, country] if p]
            loc_str = ", ".join(loc_parts) if loc_parts else None

            desc = item.findtext("description") or title
            role = item.findtext("tt:role", namespaces=namespaces)
            dept = item.findtext("tt:department", namespaces=namespaces)

            # Detect remote from description or title
            is_remote = "remote" in title.lower() or (loc_str and "remote" in loc_str.lower())
            remote_val = "remote" if is_remote else "on-site"

            provenance = DiscoveryProvenanceDTO(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                source_id=candidate.source_id,
                source_type="direct_ats",
                source_url=candidate.target_url,
                source_job_id=job_id,
                apply_url=link,
                provider_name=self.ats_name,
            )

            raw_job = RawJob(
                provenance=provenance,
                title=title[:255],
                company=company_name[:255],
                description=desc[:50000],
                location=loc_str[:255] if loc_str else None,
                remote_status=remote_val[:64],
                employment_type=str(role or dept or "Full-time")[:128],
                provider_metadata={"department": dept or ""}
            )
            jobs.append(raw_job)

        return jobs

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

# Matches: {tenant}.keka.com or custom domains
_KEKA_URL_PATTERN = re.compile(
    r"^(?:https?://)?([a-zA-Z0-9_-]+)\.keka\.com(?:/careers(?:/([a-zA-Z0-9_-]+))?)?",
    re.IGNORECASE,
)
_IDENTIFIER_RE = re.compile(
    r"/ats/documents/(?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/careerportal/",
    re.IGNORECASE,
)
_SCRIPT_IDENTIFIER_RE = re.compile(
    r"/careers/api/embedjobs/js/(?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)


class KekaAdapter(ATSAdapter):
    @property
    def strategy_id(self) -> str:
        return "keka_ats"

    @property
    def name(self) -> str:
        return "Keka ATS Adapter"

    @property
    def ats_name(self) -> str:
        return "Keka"

    @property
    def priority(self) -> int:
        return 10

    def extract_board_identifier(self, url: str) -> Optional[str]:
        if not url:
            return None
        match = _KEKA_URL_PATTERN.match(url.strip())
        if match:
            tenant = match.group(1).lower()
            portal = match.group(2)
            return f"{tenant}:{portal}" if portal else tenant
        return None

    def recognizes_url(self, url: str) -> bool:
        return "keka.com" in url.lower()

    def generate_candidates(self, url: str = None, source: SourceConfig = None) -> list[StrategyCandidate]:
        source_id = source.source_id if source else None
        board_token = self.resolve_board_identifier(url, source)
        if not board_token:
            return []

        tenant = board_token.split(":")[0]
        portal = board_token.split(":")[1] if ":" in board_token else "default"

        # Keka careers page bootstrap URL
        target_url = f"https://{tenant}.keka.com/careers"
        return [
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=target_url,
                evidence=f"Keka tenant: {tenant}",
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
            match = re.search(r"https?://([a-zA-Z0-9_-]+)\.keka\.com", url)
            tenant = match.group(1) if match else "unknown"

            # 1. Fetch careers HTML to extract organization portal identifier
            resp_bytes = await http_client.get(
                url,
                headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": "JobClaw/1.0 (South India ATS Discovery)"},
            )
            result.requests_attempted += 1
            html_text = resp_bytes.decode("utf-8", errors="replace")

            # Extract the UUID identifier
            identifier_match = _IDENTIFIER_RE.search(html_text) or _SCRIPT_IDENTIFIER_RE.search(html_text)
            raw_jobs: list[RawJob] = []

            if identifier_match:
                identifier = identifier_match.group("id")
                api_url = f"https://{tenant}.keka.com/careers/api/embedjobs/default/active/{identifier}"
                try:
                    jobs_bytes = await http_client.get(
                        api_url,
                        headers={"Accept": "application/json", "User-Agent": "JobClaw/1.0 (South India ATS Discovery)"},
                    )
                    result.requests_attempted += 1
                    raw_jobs = await self.extract_jobs(jobs_bytes, candidate)
                except Exception as api_err:
                    logger.debug(f"Keka direct embed API error: {api_err}")

            # Fallback if no identifier match or embed API failed: regex parse HTML
            if not raw_jobs:
                raw_jobs = await self._parse_keka_html(html_text, candidate, tenant)

            result.raw_jobs = raw_jobs
            result.jobs_discovered = len(raw_jobs)
            result.success = True

        except Exception as e:
            logger.warning(f"Keka adapter failed for {candidate.target_url}: {e}")
            result.success = False
            result.requests_attempted += 1
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
        match = re.search(r"https?://([a-zA-Z0-9_-]+)\.keka\.com", candidate.target_url)
        tenant = match.group(1) if match else "unknown"
        try:
            data = json.loads(response_data.decode("utf-8", errors="replace"))
        except Exception:
            return []

        if not isinstance(data, list):
            return []

        jobs: list[RawJob] = []
        for item in data:
            if not isinstance(item, dict):
                continue

            job_id = str(item.get("id") or item.get("jobId") or item.get("jobIdentifier") or item.get("identifier") or "").strip()
            title = (item.get("title") or item.get("jobTitle") or "").strip()
            if not title or not job_id:
                continue

            # Location formatting
            locs = item.get("jobLocations") or []
            if isinstance(locs, list) and locs:
                loc_names = [f"{l.get('city', '')}, {l.get('country', '')}".strip(', ') for l in locs if isinstance(l, dict)]
                location_str = ", ".join([l for l in loc_names if l])
            else:
                location_str = str(item.get("location") or "")

            if len(location_str) > 500:
                location_str = location_str[:497] + "..."

            is_remote = False
            if "remote" in location_str.lower() or "hybrid" in location_str.lower():
                is_remote = True

            dept = item.get("departmentName") or item.get("department") or ""
            exp = item.get("experience") or ""
            desc = item.get("description") or ""
            job_url = f"https://{tenant}.keka.com/careers/jobdetails/{job_id}"

            full_desc = f"{title}\nDepartment: {dept}\nExperience: {exp}\nLocation: {location_str}\n\n{desc}"

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
                employment_type="full-time",
                remote_status="remote" if is_remote else "on-site",
                url=job_url,
                apply_url=job_url,
                provider_metadata={"department": dept, "experience": exp, "job_id": job_id}
            )
            jobs.append(job)

        return jobs

    async def _parse_keka_html(
        self,
        html_text: str,
        candidate: StrategyCandidate,
        tenant: str,
    ) -> list[RawJob]:
        jobs: list[RawJob] = []
        # Fallback 1: pattern for jobs rendered in JSON script block
        script_match = re.search(r"var\s+initialData\s*=\s*(\{.*?\});", html_text, re.DOTALL)
        if script_match:
            try:
                data = json.loads(script_match.group(1))
                active_jobs = data.get("jobs") or data.get("activeJobs") or []
                if isinstance(active_jobs, list):
                    extracted = await self.extract_jobs(json.dumps(active_jobs).encode(), candidate)
                    if extracted:
                        return extracted
            except Exception:
                pass

        # Fallback 2: regex parse direct /careers/jobdetails/{id} anchor tags in HTML
        for a in re.finditer(r'href=["\'](?:https?://[^/]+)?/careers/jobdetails/(\d+)["\'][^>]*>(.*?)</a>', html_text, re.IGNORECASE):
            jid = a.group(1).strip()
            jtitle = re.sub(r'<[^>]+>', '', a.group(2)).strip()
            if jid and jtitle and len(jtitle) > 2:
                jurl = f"https://{tenant}.keka.com/careers/jobdetails/{jid}"
                prov = DiscoveryProvenanceDTO(
                    source_id=candidate.source_id,
                    strategy_id=self.strategy_id,
                    source_type="direct_ats",
                    source_url=candidate.target_url,
                    source_job_id=jid,
                    apply_url=jurl,
                    confidence_score=candidate.confidence,
                    ats_platform=self.ats_name,
                    job_board_token=tenant,
                )
                jobs.append(
                    RawJob(
                        provenance=prov,
                        title=jtitle[:512],
                        company=tenant.title()[:256],
                        location="India",
                        description=jtitle,
                        employment_type="full-time",
                        remote_status="on-site",
                        url=jurl,
                        apply_url=jurl,
                        provider_metadata={"job_id": jid}
                    )
                )
        return jobs

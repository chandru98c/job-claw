"""
Workday ATS Adapter.

Workday exposes a public JSON API at:
  POST https://{tenant}.wd5.myworkdayjobs.com/wday/cxs/{tenant}/{board}/jobs

This adapter:
  - Recognizes Workday subdomain URL patterns
  - Extracts tenant + board from the URL
  - POSTs to the canonical Workday jobs API with pagination
  - Parses the JSON response into bounded RawJob objects
"""
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
    MAX_TITLE_LEN,
    MAX_COMPANY_LEN,
    MAX_LOCATION_LEN,
    MAX_DESCRIPTION_LEN,
)
from app.core.http import SafeHTTPClient

logger = logging.getLogger(__name__)

# Pattern: {tenant}.wd1/wd2/wd3/wd5.myworkdayjobs.com/{board}
_WORKDAY_PATTERN = re.compile(
    r"^https?://([a-zA-Z0-9_-]+)\.(wd\d+)\.myworkdayjobs\.com(?:/([a-zA-Z0-9_/-]+))?",
    re.IGNORECASE,
)

# Known board names for major Indian companies (tenant → board)
_KNOWN_BOARDS: dict[str, str] = {
    "hcltech":    "HCLTechCareers",
    "cognizant":  "Cognizant_Careers",
    "capgemini":  "Capgemini",
    "accenture":  "AccentureCareers",
    "dxc":        "DXCCareers",
    "wipro":      "Wipro",
    "infosys":    "InfyTQ",
    "tcs":        "TCS",
    "mphasis":    "Mphasis",
    "hexaware":   "Hexaware",
    "ltimindtree":"LTIMindtree",
    "lntinfotech": "LTI",
    "niit":       "NIIT",
    "oracle":     "oracle",
    "sap":        "SAP",
    "ibm":        "IBM",
    "dell":       "dell",
    "hp":         "HP",
    "cisco":      "Cisco",
    "amazon":     "Amazon_Jobs",
    "google":     "Google",
    "microsoft":  "Microsoft",
}


class WorkdayAdapter(ATSAdapter):
    """
    ATS adapter for Workday job boards.
    Covers HCL, Cognizant, Capgemini, Accenture India and all Workday tenants.
    """

    @property
    def strategy_id(self) -> str:
        return "workday_ats"

    @property
    def name(self) -> str:
        return "Workday ATS Adapter"

    @property
    def ats_name(self) -> str:
        return "Workday"

    @property
    def priority(self) -> int:
        return 10

    @property
    def capabilities(self) -> dict:
        return {
            "supports_pagination": True,
            "supports_json_api": True,
            "max_jobs_per_request": 20,
        }

    def extract_board_identifier(self, url: str) -> Optional[str]:
        """Extract tenant from a Workday URL."""
        match = _WORKDAY_PATTERN.match(url)
        if match:
            return match.group(1).lower()
        return None

    def _extract_tenant_cluster_and_board(self, url: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        match = _WORKDAY_PATTERN.match(url)
        if not match:
            return None, None, None
        tenant = match.group(1).lower()
        cluster = match.group(2).lower() if match.group(2) else "wd5"
        # board is the path segment after the domain, or look up known boards
        path_segment = match.group(3) or ""
        board = path_segment.strip("/").split("/")[0] if path_segment.strip("/") else None
        if not board:
            board = _KNOWN_BOARDS.get(tenant, f"{tenant}Careers")
        return tenant, cluster, board

    def recognizes_url(self, url: str) -> bool:
        return self.extract_board_identifier(url) is not None

    def can_handle(self, source: SourceConfig) -> bool:
        return bool(source.ats_type and source.ats_type.lower() == "workday")

    def generate_candidates(self, url: str = None, source: SourceConfig = None) -> list[StrategyCandidate]:
        source_id = source.source_id if source else None
        cluster = "wd5"

        if source and source.identifier:
            # identifier format: "tenant/board"
            parts = source.identifier.split("/", 1)
            tenant = parts[0]
            board = parts[1] if len(parts) > 1 else _KNOWN_BOARDS.get(tenant, f"{tenant}Careers")
            if source.base_url:
                m = _WORKDAY_PATTERN.match(source.base_url)
                if m:
                    cluster = m.group(2).lower()
        elif url:
            tenant, cluster, board = self._extract_tenant_cluster_and_board(url)
        else:
            return []

        if not tenant or not board:
            return []

        # Workday API with preserved cluster
        api_url = f"https://{tenant}.{cluster}.myworkdayjobs.com/wday/cxs/{tenant}/{board}/jobs"

        return [
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=api_url,
                evidence=f"Workday tenant: {tenant}, cluster: {cluster}, board: {board}",
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
            payload = json.dumps({"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""})
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            }
            response_data = await http_client.request("POST", url, content=payload, headers=headers)
            result.requests_attempted = 1

            raw_jobs = await self.extract_jobs(response_data, candidate)
            result.raw_jobs = raw_jobs
            result.jobs_discovered = len(raw_jobs)

        except Exception as e:
            logger.error(f"Workday adapter failed for {candidate.candidate_id}: {e}")
            result.success = False
            result.requests_attempted = 1
            error_type = DiscoveryErrorType.NETWORK_FAILURE
            if "403" in str(e) or "404" in str(e):
                error_type = DiscoveryErrorType.REQUIRES_BROWSER_FALLBACK
            elif "parse" in str(e).lower() or "json" in str(e).lower():
                error_type = DiscoveryErrorType.PARSING_FAILURE
            result.errors.append(
                DiscoveryError(
                    error_type=error_type,
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
        """
        Parse Workday API JSON response.

        Expected structure:
        {
          "jobPostings": [
            {
              "title": "...",
              "locationsText": "Chennai, Tamil Nadu, India",
              "externalPath": "/job/Chennai/...",
              "postedOn": "...",
              "bulletFields": ["..."]
            }
          ],
          "total": N
        }
        """
        try:
            data = json.loads(response_data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Workday: failed to parse JSON: {e}")
            return []

        if not isinstance(data, dict):
            return []

        postings = data.get("jobPostings", [])
        if not isinstance(postings, list):
            return []

        tenant = self.extract_board_identifier(candidate.target_url) or "unknown"
        # Build base URL for apply links: https://{tenant}.wd5.myworkdayjobs.com
        import urllib.parse
        parsed = urllib.parse.urlparse(candidate.target_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        raw_jobs: list[RawJob] = []

        for posting in postings:
            try:
                if not isinstance(posting, dict):
                    continue

                title = str(posting.get("title", ""))[:MAX_TITLE_LEN]
                if not title:
                    continue

                location = str(posting.get("locationsText", "") or "")[:MAX_LOCATION_LEN] or None
                external_path = str(posting.get("externalPath", "") or "")
                apply_url = (base_url + external_path) if external_path else None

                # job ID from path
                job_id = external_path.rstrip("/").split("/")[-1] if external_path else ""

                description_parts = posting.get("bulletFields", [])
                description = " | ".join(str(p) for p in description_parts if p)[:MAX_DESCRIPTION_LEN] or None

                raw_jobs.append(
                    RawJob(
                        provenance=DiscoveryProvenanceDTO(
                            strategy_id=self.strategy_id,
                            adapter_id=self.strategy_id,
                            source_id=candidate.source_id,
                            source_type="direct_ats",
                            source_url=candidate.target_url,
                            source_job_id=job_id[:256] if job_id else None,
                            apply_url=apply_url,
                            provider_name=self.ats_name,
                        ),
                        title=title,
                        company=tenant[:MAX_COMPANY_LEN],
                        location=location,
                        description=description,
                    )
                )
            except Exception as e:
                logger.warning(f"Workday: skipping malformed posting: {e}")
                continue

        return raw_jobs

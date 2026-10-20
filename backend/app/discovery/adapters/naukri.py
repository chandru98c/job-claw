"""
Naukri Aggregator Adapter.

Naukri.com is the dominant Indian job portal (~70% market share).
It exposes a semi-public search API used by its own frontend.

API endpoint:
  GET https://www.naukri.com/jobapi/v3/search
      ?noOfResults=20&urlType=search_by_keyword
      &searchType=adv&keyword={q}&location={location}
      &experience=0&jobAge=1
  Headers: appid=109, systemid=109

This adapter:
  - Recognizes naukri.com URLs
  - Builds search API requests from source config (keyword + location)
  - Parses the JSON response into bounded RawJob objects
  - Supports pagination up to 5 pages (100 jobs max per run)
"""
import os
import json
import re
import time
import logging
import urllib.parse
from typing import Optional

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
    MAX_DESCRIPTION_LEN,
)
from app.core.http import SafeHTTPClient

logger = logging.getLogger(__name__)

_NAUKRI_PATTERN = re.compile(
    r"^https?://(?:www\.)?naukri\.com",
    re.IGNORECASE,
)

_NAUKRI_API = "https://www.naukri.com/jobapi/v3/search"
_NAUKRI_HEADERS = {
    "authority": "www.naukri.com",
    "appid": "109",
    "systemid": "Naukri",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}
if os.getenv("NAUKRI_NKPARAM"):
    _NAUKRI_HEADERS["Nkparam"] = os.environ["NAUKRI_NKPARAM"]


MAX_PAGES = 5
PAGE_SIZE = 20


class NaukriAdapter(ATSAdapter):
    """
    Aggregator adapter for Naukri.com — India's largest job portal.
    Searches by keyword + location, returns structured job listings.
    """

    @property
    def strategy_id(self) -> str:
        return "naukri_aggregator"

    @property
    def name(self) -> str:
        return "Naukri Aggregator Adapter"

    @property
    def ats_name(self) -> str:
        return "Naukri"

    @property
    def priority(self) -> int:
        return 15  # Slightly lower than direct ATS, higher than heuristics

    @property
    def category(self) -> StrategyCategory:
        return StrategyCategory.AGGREGATOR

    @property
    def capabilities(self) -> dict:
        return {
            "supports_pagination": True,
            "supports_json_api": True,
            "max_jobs_per_request": PAGE_SIZE * MAX_PAGES,
        }

    def extract_board_identifier(self, url: str) -> Optional[str]:
        """For Naukri, the 'identifier' is the search keyword embedded in the URL."""
        try:
            parsed = urllib.parse.urlparse(url)
            # e.g. /mca-jobs-in-chennai → keyword=mca, location=chennai
            path = parsed.path.lower()
            match = re.search(r"/([a-z0-9-]+)-jobs(?:-in-([a-z0-9-]+))?", path)
            if match:
                return match.group(1)
        except Exception:
            pass
        return "software"  # default keyword

    def recognizes_url(self, url: str) -> bool:
        return bool(_NAUKRI_PATTERN.match(url))

    def can_handle(self, source: SourceConfig) -> bool:
        return bool(source.ats_type and source.ats_type.lower() == "naukri")

    def _parse_keyword_location(self, url: str) -> tuple[str, str]:
        """Extract keyword and location from a Naukri URL."""
        try:
            parsed = urllib.parse.urlparse(url)
            path = parsed.path.lower()
            # /mca-jobs-in-chennai or /software-developer-jobs-in-chennai
            match = re.search(r"/([a-z0-9-]+)-jobs(?:-in-([a-z0-9-]+))?", path)
            if match:
                keyword = match.group(1).replace("-", " ")
                location = (match.group(2) or "").replace("-", " ")
                return keyword, location
        except Exception:
            pass
        return "software developer", "chennai"

    def generate_candidates(self, url: str = None, source: SourceConfig = None) -> list[StrategyCandidate]:
        source_id = source.source_id if source else None

        if source and source.identifier:
            # identifier format: "keyword|location"
            parts = source.identifier.split("|", 1)
            keyword = parts[0].strip()
            location = parts[1].strip() if len(parts) > 1 else "chennai"
        elif url:
            keyword, location = self._parse_keyword_location(url)
        else:
            keyword, location = "software developer", "chennai"

        params = urllib.parse.urlencode({
            "noOfResults": PAGE_SIZE,
            "urlType": "search_by_keyword",
            "searchType": "adv",
            "keyword": keyword,
            "location": location,
            "experience": 0,
            "jobAge": 7,
        })
        api_url = f"{_NAUKRI_API}?{params}"

        return [
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=api_url,
                evidence=f"Naukri search: keyword={keyword}, location={location}",
                confidence=0.9,
                source="naukri_search_api",
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

        all_jobs: list[RawJob] = []
        base_url = candidate.validated_url or candidate.target_url

        try:
            for page in range(MAX_PAGES):
                offset = page * PAGE_SIZE
                # Inject pageNo into URL
                page_url = re.sub(r"noOfResults=\d+", f"noOfResults={PAGE_SIZE}", base_url)
                if "start=" in page_url:
                    page_url = re.sub(r"start=\d+", f"start={offset}", page_url)
                else:
                    page_url += f"&start={offset}"

                response_data = await http_client.get(page_url, headers=_NAUKRI_HEADERS)
                result.requests_attempted += 1

                page_jobs = await self.extract_jobs(response_data, candidate)
                all_jobs.extend(page_jobs)

                # Stop paginating if we got fewer than a full page
                if len(page_jobs) < PAGE_SIZE:
                    break

            result.raw_jobs = all_jobs
            result.jobs_discovered = len(all_jobs)

        except Exception as e:
            logger.error(f"Naukri adapter failed for {candidate.candidate_id}: {e}")
            result.success = False
            error_type = DiscoveryErrorType.NETWORK_FAILURE
            if "403" in str(e) or "429" in str(e):
                error_type = DiscoveryErrorType.STRATEGY_UNAVAILABLE
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
        Parse Naukri API JSON response.

        Expected structure:
        {
          "jobDetails": [
            {
              "jobId": "...",
              "title": "...",
              "companyName": "...",
              "placeholders": [
                {"label": "location", "value": "Chennai"},
                {"label": "experience", "value": "0-2 Yrs"}
              ],
              "jdURL": "https://www.naukri.com/job-listings-...",
              "jobDescription": "..."
            }
          ],
          "noOfJobs": 150
        }
        """
        try:
            data = json.loads(response_data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Naukri: failed to parse JSON: {e}")
            return []

        if not isinstance(data, dict):
            return []

        job_details = data.get("jobDetails", [])
        if not isinstance(job_details, list):
            return []

        raw_jobs: list[RawJob] = []

        for job in job_details:
            try:
                if not isinstance(job, dict):
                    continue

                title = str(job.get("title", ""))[:MAX_TITLE_LEN]
                if not title:
                    continue

                company = str(job.get("companyName", "") or "")[:MAX_COMPANY_LEN]
                job_id = str(job.get("jobId", "") or "")
                apply_url = str(job.get("jdURL", "") or "")[:2048] or None
                description = str(job.get("jobDescription", "") or "")[:MAX_DESCRIPTION_LEN] or None

                # Extract location from placeholders array
                location = None
                placeholders = job.get("placeholders", [])
                if isinstance(placeholders, list):
                    for ph in placeholders:
                        if isinstance(ph, dict) and ph.get("label") == "location":
                            location = str(ph.get("value", ""))[:MAX_LOCATION_LEN] or None
                            break

                # Fallback location fields
                if not location:
                    location = str(job.get("location", "") or "")[:MAX_LOCATION_LEN] or None

                raw_jobs.append(
                    RawJob(
                        provenance=DiscoveryProvenanceDTO(
                            strategy_id=self.strategy_id,
                            adapter_id=self.strategy_id,
                            source_id=candidate.source_id,
                            source_type="aggregator",
                            source_url=candidate.target_url,
                            source_job_id=job_id or None,
                            apply_url=apply_url,
                            provider_name=self.ats_name,
                        ),
                        title=title,
                        company=company or "Unknown",
                        location=location,
                        description=description,
                    )
                )
            except Exception as e:
                logger.warning(f"Naukri: skipping malformed job entry: {e}")
                continue

        return raw_jobs

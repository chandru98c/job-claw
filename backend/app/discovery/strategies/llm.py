"""
LLM Discovery Strategy.

Acts as a last-resort fallback for discovery.
Takes a URL (usually discovered via career page or sitemap), fetches the HTML,
strips it, and passes it to an LLM to extract RawJobs.
"""
from __future__ import annotations

import os
import json
import time
import logging
import urllib.parse
from typing import Optional

from app.discovery.interfaces import DiscoveryStrategy, StrategyCategory
from app.schemas.discovery import (
    StrategyCandidate,
    StrategyExecutionResult,
    DiscoveryError,
    DiscoveryErrorType,
    SourceConfig,
    RawJob,
    DiscoveryProvenanceDTO,
)
from app.core.http import SafeHTTPClient

logger = logging.getLogger(__name__)

class LLMStrategy(DiscoveryStrategy):
    """
    LLM-based job extraction strategy.
    Runs as a fallback when deterministic ATS extraction fails.
    """

    @property
    def strategy_id(self) -> str:
        return "llm_discovery"

    @property
    def name(self) -> str:
        return "LLM Assisted Discovery"

    @property
    def category(self) -> StrategyCategory:
        return StrategyCategory.LLM_ROUTED

    @property
    def priority(self) -> int:
        # Lowest priority, only runs as last resort
        return 90

    @property
    def capabilities(self) -> dict:
        return {
            "discovers_endpoints": False,
            "extracts_jobs": True,
            "max_candidates": 1,
        }

    def recognizes_url(self, url: str) -> bool:
        """
        Technically can attempt any URL, but relies on the router to only 
        invoke it when necessary.
        """
        try:
            parsed = urllib.parse.urlparse(url)
            return parsed.scheme in ("http", "https") and bool(parsed.hostname)
        except Exception:
            return False

    def generate_candidates(self, url: str = None, source: Optional[SourceConfig] = None) -> list[StrategyCandidate]:
        if not url:
            return []
        return [
            StrategyCandidate(
                strategy_id=self.strategy_id,
                target_url=url,
                evidence="Fallback execution",
                confidence=0.1,
                source="llm_router",
                priority=self.priority,
            )
        ]

    async def execute(
        self,
        candidate: StrategyCandidate,
        http_client: SafeHTTPClient,
    ) -> StrategyExecutionResult:
        start = time.monotonic()
        result = StrategyExecutionResult(
            strategy_id=self.strategy_id,
            candidate_id=candidate.candidate_id,
        )

        try:
            url = candidate.validated_url or candidate.target_url
            response_bytes = await http_client.get(url)
            result.requests_attempted += 1
            
            html = response_bytes.decode("utf-8", errors="replace")
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            
            # Remove scripts, styles, forms, headers, footers
            for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
                tag.decompose()

            # Convert anchors to markdown links [text](href) so LLM knows the target url
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                link_text = a.get_text(" ", strip=True)
                if href and not href.startswith("#") and not href.startswith("javascript:") and link_text:
                    a.replace_with(f" [{link_text}]({href}) ")

            text = soup.get_text(" ", strip=True)
            import re
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Truncate to avoid massive token usage
            text = text[:15000] 
            
            jobs_data = await self._call_llm(text)
            
            for job in jobs_data:
                try:
                    job_title = (job.get("title") or "").strip()[:256]
                    job_comp = (job.get("company") or "Unknown").strip()[:256]
                    job_apply = (job.get("apply_url") or "").strip()

                    # Needs title and company to be valid RawJob
                    if not job_title or not job_comp:
                        continue

                    # STRICT RULE: A genuine job MUST have a direct application link.
                    # Category headlines (e.g. 'contract roles', 'cxo roles', 'sales jobs')
                    # without application links are rejected.
                    if not job_apply:
                        continue

                    resolved_apply = urllib.parse.urljoin(url, job_apply)
                    parsed_apply = urllib.parse.urlparse(resolved_apply)
                    apply_path = parsed_apply.path.rstrip("/").lower()

                    # Reject if it only resolves to the generic root career/job page or category listing
                    if apply_path in (
                        "", "/careers", "/jobs", "/job-opportunities", "/career",
                        "/en-in/careers", "/en/careers", "/careers/odc-opportunities",
                        "/careers/opportunities", "/careers/consulting-jobs",
                        "/odc_opportunities", "/opportunities", "/consulting_jobs"
                    ) or apply_path.endswith(("/careers", "/jobs", "/odc_opportunities", "/opportunities")):
                        continue

                    raw_job = RawJob(
                        provenance=DiscoveryProvenanceDTO(
                            strategy_id=self.strategy_id,
                            source_type="llm_extracted",
                            source_url=url,
                            apply_url=resolved_apply,
                        ),
                        title=job_title,
                        company=job_comp,
                        location=job.get("location", None),
                        employment_type=job.get("employment_type", None),
                        remote_status=job.get("remote_status", None),
                        apply_url=resolved_apply,
                        url=resolved_apply,
                    )
                    result.raw_jobs.append(raw_job)
                except Exception as e:
                    logger.warning(f"LLM extracted invalid job format: {e}")
            
            result.success = True
            result.jobs_discovered = len(result.raw_jobs)

        except Exception as e:
            logger.warning(f"LLM fallback extraction unavailable or failed: {e}")
            result.success = False
            result.errors.append(
                DiscoveryError(
                    error_type=DiscoveryErrorType.PARSING_FAILURE,
                    strategy_id=self.strategy_id,
                    candidate_id=candidate.candidate_id,
                    message=f"LLM Extraction unavailable: {str(e)[:150]}",
                )
            )

        result.duration_seconds = time.monotonic() - start
        return result

    async def _call_llm(self, text: str) -> list[dict]:
        from pydantic import BaseModel, Field
        from app.core.llm import llm_client
        
        class ExtractedJob(BaseModel):
            title: str = Field(..., description="The specific job title (e.g. 'Software Engineer', 'Data Analyst')")
            company: str = Field(..., description="The hiring company name")
            apply_url: str | None = Field(None, description="The direct URL or link to view/apply for this specific job, extracted from markdown links [text](href)")
            location: str | None = Field(None, description="The job location")
            employment_type: str | None = Field(None, description="Employment type (e.g. Full-time, Contract)")
            remote_status: str | None = Field(None, description="Remote status (e.g. Remote, Hybrid, On-site)")

        class ExtractedJobsList(BaseModel):
            jobs: list[ExtractedJob] = Field(..., description="List of extracted jobs")
            
        prompt = f"""
        Extract only genuine, specific job openings from the following text.
        DO NOT extract general department headings, category links (e.g. 'contract roles', 'cxo roles', 'sales jobs', 'engineering jobs'), or corporate marketing blurbs.
        
        For each job opening, extract:
        - 'title': The specific job title
        - 'company': The hiring company name
        - 'apply_url': The direct link or relative URL to apply or view job details from the [text](url) anchors. Leave null if no specific job link exists.
        Optional fields: 'location', 'employment_type', 'remote_status'.
        
        TEXT:
        {text}
        """
        
        try:
            result = await llm_client.generate_structured(
                prompt=prompt,
                schema=ExtractedJobsList,
                timeout=45
            )
            # Convert back to dicts to maintain existing contract
            return [job.model_dump() for job in result.jobs]
        except Exception as e:
            logger.error(f"LLMClient failed to extract jobs: {e}")
            raise Exception(f"LLM extraction failed: {e}")

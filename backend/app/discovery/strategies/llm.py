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
            # Strip simple tags to save tokens
            import re
            text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.IGNORECASE|re.DOTALL)
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE|re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Truncate to avoid massive token usage
            text = text[:15000] 
            
            jobs_data = await self._call_llm(text)
            
            for job in jobs_data:
                try:
                    raw_job = RawJob(
                        provenance=DiscoveryProvenanceDTO(
                            strategy_id=self.strategy_id,
                            source_type="llm_extracted",
                            source_url=url,
                        ),
                        title=job.get("title", "")[:256],
                        company=job.get("company", "Unknown")[:256],
                        location=job.get("location", None),
                        employment_type=job.get("employment_type", None),
                        remote_status=job.get("remote_status", None),
                    )
                    # Needs title and company to be valid RawJob
                    if raw_job.title and raw_job.company:
                        result.raw_jobs.append(raw_job)
                except Exception as e:
                    logger.warning(f"LLM extracted invalid job format: {e}")
            
            result.success = True
            result.jobs_discovered = len(result.raw_jobs)

        except Exception as e:
            result.success = False
            result.errors.append(
                DiscoveryError(
                    error_type=DiscoveryErrorType.PARSING_FAILURE,
                    strategy_id=self.strategy_id,
                    candidate_id=candidate.candidate_id,
                    message=f"LLM Extraction failed: {str(e)}",
                )
            )

        result.duration_seconds = time.monotonic() - start
        return result

    async def _call_llm(self, text: str) -> list[dict]:
        import aiohttp
        groq_key = os.environ.get("GROQ_API_KEY")
        model = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
        
        if not groq_key:
            raise Exception("No LLM API key configured in environment")
            
        prompt = f"""
        Extract job listings from the following text.
        Return ONLY a JSON array of objects.
        Each object must have: 'title', 'company'.
        Optional fields: 'location', 'employment_type', 'remote_status'.
        
        TEXT:
        {text}
        """
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"}
                },
                timeout=30
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise Exception(f"LLM API returned {resp.status}: {body}")
                data = await resp.json()
                content = data["choices"][0]["message"]["content"]
                
                parsed = json.loads(content)
                # handle if wrapped in a dict
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        if isinstance(v, list):
                            return v
                    return []
                elif isinstance(parsed, list):
                    return parsed
                return []

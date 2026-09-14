import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from app.schemas.discovery import (
    StrategyCandidate, 
    CandidateState, 
    DiscoveryErrorType, 
    StrategyExecutionResult,
    DiscoveryError
)
from app.acquisition.base import AcquisitionResult
from app.discovery.pipeline import CandidatePipeline
from app.discovery.registry import StrategyRegistry
from app.discovery.interfaces import DiscoveryStrategy
from app.core.http import DomainPolicy
from app.core.security import SSRFViolationError

# Mock Strategy that always requests browser fallback
class MockFallbackStrategy(DiscoveryStrategy):
    @property
    def strategy_id(self): return "mock_fallback"
    @property
    def name(self): return "Mock Fallback"
    @property
    def category(self): return "ATS_ADAPTER"
    
    def recognizes_url(self, url): return True
    def generate_candidates(self, url): return []
    
    async def execute(self, candidate, http_client):
        # Simulates returning HTTP insufficient
        return StrategyExecutionResult(
            strategy_id=self.strategy_id,
            candidate_id=candidate.candidate_id,
            success=False,
            errors=[DiscoveryError(
                error_type=DiscoveryErrorType.REQUIRES_BROWSER_FALLBACK,
                message="Need browser"
            )]
        )

    async def extract_jobs(self, response_data, candidate):
        from app.schemas.discovery import RawJob, DiscoveryProvenanceDTO
        return [
            RawJob(
                provenance=DiscoveryProvenanceDTO(
                    strategy_id=self.strategy_id,
                    source_type="direct_ats",
                    source_url="http://test.com",
                    provider_name="Mock"
                ),
                title="Browser Job",
                company="MockCo",
                location="Remote"
            )
        ]


@pytest.mark.asyncio
async def test_pipeline_triggers_browser_fallback():
    registry = StrategyRegistry()
    registry.register(MockFallbackStrategy())
    
    pipeline = CandidatePipeline(registry)
    candidate = StrategyCandidate(
        strategy_id="mock_fallback",
        target_url="http://test.com",
        state=CandidateState.VALIDATED,
        validated_url="http://test.com"
    )
    
    # Mock BrowserAcquisition to return success
    with patch("app.acquisition.browser.BrowserAcquisition.acquire", new_callable=AsyncMock) as mock_acquire:
        mock_acquire.return_value = AcquisitionResult(
            success=True,
            method="BROWSER",
            bounded_content=b"<html>JS jobs here</html>"
        )
        
        result = await pipeline.execute_candidate(candidate)
        
        assert mock_acquire.called
        assert result.success is True
        assert result.jobs_discovered == 1
        assert result.raw_jobs[0].title == "Browser Job"
        assert len(result.errors) == 0 # The fallback error should be removed


@pytest.mark.asyncio
async def test_browser_policy_ssrf_blocked():
    from app.acquisition.browser import BrowserAcquisition, BrowserPolicy
    from playwright.async_api import Route, Request
    
    browser = BrowserAcquisition(domain_policy=DomainPolicy())
    
    # Mock route and request
    route = AsyncMock(spec=Route)
    request = MagicMock(spec=Request)
    request.url = "http://169.254.169.254/latest/meta-data/"
    request.resource_type = "document"
    request.is_navigation_request.return_value = True
    
    await browser._handle_route(route, request)
    
    # Ensure route was aborted due to SSRF
    route.abort.assert_called_with("accessdenied")


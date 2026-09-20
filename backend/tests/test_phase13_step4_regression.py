import pytest
import uuid
from app.database.models import Job, JobStatus, JobVersion
from app.canonicalization.identity import resolve_identity
from app.schemas.discovery import RawJob

from app.verification.verifier import VerificationEngine
from app.schemas.verification import VerificationOutcome, VerificationReason
from app.core.http import SafeHTTPClient, httpx
from unittest.mock import patch, MagicMock

from app.schemas.discovery import RawJob, DiscoveryProvenanceDTO
from app.core.security import UrlValidator

@pytest.mark.asyncio
async def test_freshness_regression():
    """
    Test freshness regression handling.
    404 / 410 -> missing evidence -> EXPIRED (CONFIRMED_MISSING)
    403 -> remote restriction -> UNKNOWN (AMBIGUOUS)
    429 / 5xx / timeout -> UNKNOWN (TRANSIENT_FAILURE)
    """
    class MockResponse:
        def __init__(self, status_code):
            self.status_code = status_code

    async def mock_get_404(*args, **kwargs):
        raise httpx.HTTPStatusError("404 Not Found", request=MagicMock(), response=MockResponse(404))
        
    async def mock_get_403(*args, **kwargs):
        raise httpx.HTTPStatusError("403 Forbidden", request=MagicMock(), response=MockResponse(403))
        
    async def mock_get_500(*args, **kwargs):
        raise httpx.HTTPStatusError("500 Server Error", request=MagicMock(), response=MockResponse(500))

    # Mock UrlValidator so we don't hit policy blocking for dummy domains
    with patch.object(UrlValidator, 'validate_and_resolve', return_value="http://test.com"):
        # 404 should confirm missing
        with patch.object(SafeHTTPClient, 'get', side_effect=mock_get_404):
            res1 = await VerificationEngine.verify_url("http://test.com/404")
            assert res1.outcome == VerificationOutcome.CONFIRMED_MISSING

        # 403 should mark AMBIGUOUS
        with patch.object(SafeHTTPClient, 'get', side_effect=mock_get_403):
            res2 = await VerificationEngine.verify_url("http://test.com/403")
            assert res2.outcome == VerificationOutcome.AMBIGUOUS

        # 5xx should mark TRANSIENT_FAILURE
        with patch.object(SafeHTTPClient, 'get', side_effect=mock_get_500):
            res3 = await VerificationEngine.verify_url("http://test.com/500")
            assert res3.outcome == VerificationOutcome.TRANSIENT_FAILURE

def test_canonicalization_identity_regression():
    """
    Test permutations of identity resolution logic.
    """
    from sqlalchemy.orm import Session
    from unittest.mock import MagicMock
    
    db = MagicMock(spec=Session)
    
    # Simulate DB lookup returning an existing JobSourceProvenance for the same ATS ID
    mock_prov = MagicMock()
    mock_prov.job = Job(id="existing_job", canonical_apply_url="https://test.com/apply")
    
    db.query().filter().first.return_value = mock_prov
    
    # 1. Exact ATS ID match
    r_job = RawJob(
            provenance=DiscoveryProvenanceDTO(
                strategy_id="test",
                source_id="mock_source",
                source_type="direct_ats",
                source_url="https://test.com/jobs",
                source_job_id="123"
            ),
        title="Engineer",
        company="Tech",
        provider_metadata={"ats_id": "123"}
    )
    
    matched_job = resolve_identity(db, r_job)
    assert matched_job is not None
    assert matched_job.id == "existing_job"
    
def test_search_scoring_regression():
    """
    Deterministic scoring bounds check.
    TITLE_MATCH: 40
    SKILL_MATCH: 30
    LOCATION_MATCH: 15
    REMOTE_MATCH: 10
    EMPLOYMENT_TYPE_MATCH: 5
    """
    import asyncio
    from app.services.search import SearchService
    from app.database.models import Profile, Job, JobStatus
    
    # We will mock the database returning a specific list of jobs
    class MockResult:
        def __init__(self, jobs):
            self.jobs = jobs
        def scalars(self):
            return self
        def all(self):
            return self.jobs
            
    class AsyncMockSession:
        async def execute(self, stmt):
            return MockResult([job])
            
    db = AsyncMockSession()
    
    profile = Profile(
        id=str(uuid.uuid4()),
        interested_fields=["software engineer"],
        skills=["react"],
        location="New York",
        preferred_job_types=["FULL_TIME"],
        preferred_locations=["remote"]
    )
    
    job = Job(
        id=str(uuid.uuid4()),
        title="Senior Software Engineer",
        description="We use React and Python.",
        location="New York, NY",
        remote_status="REMOTE",
        job_type="FULL_TIME",
        status=JobStatus.ACTIVE
    )
    
    async def run_test():
        results, total = await SearchService.match_candidate(db, profile)
        assert total == 1
        assert results[0]["score"] == 100 # 40 + 30 + 15 + 10 + 5
        
        reasons = results[0]["reasons"]
        assert "TITLE_MATCH" in reasons
        assert "SKILL_MATCH" in reasons
        assert "LOCATION_MATCH" in reasons
        assert "REMOTE_MATCH" in reasons
        assert "EMPLOYMENT_TYPE_MATCH" in reasons
        
    asyncio.run(run_test())

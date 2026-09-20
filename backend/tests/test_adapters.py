"""
Tests for the Greenhouse ATS Adapter.

All tests use mocked HTTP responses — no network access.
"""
import pytest
import json
from unittest import mock

from app.discovery.adapters.greenhouse import GreenhouseAdapter
from app.discovery.registry import StrategyRegistry
from app.discovery.pipeline import CandidatePipeline
from app.core.http import SafeHTTPClient, DomainPolicy
from app.schemas.discovery import (
    StrategyCandidate,
    CandidateState,
)


@pytest.fixture
def adapter():
    return GreenhouseAdapter()


# ─── Greenhouse Sample Responses ────────────────────────────────────────────

SAMPLE_GREENHOUSE_RESPONSE = json.dumps({
    "jobs": [
        {
            "id": 12345,
            "title": "Software Engineer",
            "location": {"name": "San Francisco, CA"},
            "content": "<p>Build great software.</p>",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/12345",
            "departments": [{"name": "Engineering"}],
            "updated_at": "2024-01-15T10:00:00Z",
        },
        {
            "id": 67890,
            "title": "Product Manager",
            "location": {"name": "New York, NY"},
            "content": "<p>Lead product development.</p>",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/67890",
            "departments": [{"name": "Product"}],
        },
    ]
}).encode("utf-8")

MALFORMED_RESPONSE = b'{"jobs": "not_a_list"}'
EMPTY_RESPONSE = json.dumps({"jobs": []}).encode("utf-8")
INVALID_JSON = b"<html>not json</html>"
PARTIAL_JOBS_RESPONSE = json.dumps({
    "jobs": [
        {"id": 1, "title": "Good Job", "location": {"name": "LA"}, "content": "ok", "absolute_url": "https://x.com/1"},
        {"id": 2},  # Missing title — should be skipped
        "not_a_dict",  # Should be skipped
        {"id": 3, "title": "", "location": {"name": "LA"}},  # Empty title — skipped
    ]
}).encode("utf-8")


# ─── URL Recognition Tests ─────────────────────────────────────────────────

class TestGreenhouseRecognition:

    def test_recognizes_api_url(self, adapter):
        assert adapter.recognizes_url("https://boards-api.greenhouse.io/v1/boards/acme/jobs")

    def test_recognizes_board_url(self, adapter):
        assert adapter.recognizes_url("https://boards.greenhouse.io/acme")

    def test_recognizes_board_url_with_path(self, adapter):
        assert adapter.recognizes_url("https://boards.greenhouse.io/acme/jobs/12345")

    def test_recognizes_subdomain(self, adapter):
        assert adapter.recognizes_url("https://acme.greenhouse.io/some/path")

    def test_rejects_reserved_subdomain(self, adapter):
        assert not adapter.recognizes_url("https://boards.greenhouse.io")
        assert not adapter.recognizes_url("https://www.greenhouse.io")
        assert not adapter.recognizes_url("https://api.greenhouse.io")
        assert not adapter.recognizes_url("https://app.greenhouse.io")

    def test_rejects_unrelated_url(self, adapter):
        assert not adapter.recognizes_url("https://example.com/jobs")
        assert not adapter.recognizes_url("https://lever.co/company/jobs")

    def test_rejects_invalid_greenhouse_url(self, adapter):
        assert not adapter.recognizes_url("https://greenhouse.io")  # No board token

    def test_extract_board_from_api_url(self, adapter):
        assert adapter.extract_board_identifier(
            "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
        ) == "acme"

    def test_extract_board_from_board_url(self, adapter):
        assert adapter.extract_board_identifier(
            "https://boards.greenhouse.io/acme"
        ) == "acme"

    def test_extract_board_from_subdomain(self, adapter):
        assert adapter.extract_board_identifier(
            "https://acme.greenhouse.io/"
        ) == "acme"


# ─── Candidate Generation Tests ────────────────────────────────────────────

class TestGreenhouseCandidateGeneration:

    def test_generates_api_candidate(self, adapter):
        candidates = adapter.generate_candidates("https://boards.greenhouse.io/acme")
        assert len(candidates) == 1
        assert "boards-api.greenhouse.io" in candidates[0].target_url
        assert "acme" in candidates[0].target_url
        assert candidates[0].state == CandidateState.DISCOVERED

    def test_does_not_generate_for_unknown_url(self, adapter):
        candidates = adapter.generate_candidates("https://example.com/jobs")
        assert candidates == []

    def test_constructed_api_url_is_safe(self, adapter):
        """The constructed API URL should always be the canonical endpoint."""
        candidates = adapter.generate_candidates("https://boards.greenhouse.io/acme/../../../etc/passwd")
        if candidates:
            for c in candidates:
                assert "boards-api.greenhouse.io/v1/boards/" in c.target_url
                assert "etc/passwd" not in c.target_url


# ─── Extraction Tests ──────────────────────────────────────────────────────

class TestGreenhouseExtraction:

    @pytest.mark.asyncio
    async def test_extract_valid_jobs(self, adapter):
        candidate = StrategyCandidate(
            strategy_id="greenhouse_ats",
            target_url="https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
        )
        jobs = await adapter.extract_jobs(SAMPLE_GREENHOUSE_RESPONSE, candidate)
        assert len(jobs) == 2
        assert jobs[0].title == "Software Engineer"
        assert jobs[0].company == "acme"
        assert jobs[0].location == "San Francisco, CA"
        assert jobs[0].provenance.strategy_id == "greenhouse_ats"
        assert jobs[0].provenance.source_job_id == "12345"
        assert jobs[0].provenance.provider_name == "Greenhouse"

    @pytest.mark.asyncio
    async def test_extract_airbnb_regression(self, adapter):
        """
        Regression test: Ensure that multiple jobs in a Greenhouse response
        produce distinct RawJobs with unique stable external IDs and apply URLs,
        so they do not collapse into 1 canonical job downstream.
        """
        from app.schemas.discovery import SourceConfig
        candidate = StrategyCandidate(
            strategy_id="greenhouse_ats",
            target_url="https://boards-api.greenhouse.io/v1/boards/airbnb/jobs?content=true",
        )
        jobs = await adapter.extract_jobs(SAMPLE_GREENHOUSE_RESPONSE, candidate)
        assert len(jobs) == 2
        assert jobs[0].provenance.source_job_id == "12345"
        assert jobs[1].provenance.source_job_id == "67890"
        assert jobs[0].provenance.apply_url == "https://boards.greenhouse.io/acme/jobs/12345"
        assert jobs[1].provenance.apply_url == "https://boards.greenhouse.io/acme/jobs/67890"
        
        # Verify they are unique
        job_ids = set([j.provenance.source_job_id for j in jobs])
        apply_urls = set([j.provenance.apply_url for j in jobs])
        
        assert len(job_ids) == 2
        assert len(apply_urls) == 2

    @pytest.mark.asyncio
    async def test_extract_empty_jobs(self, adapter):
        candidate = StrategyCandidate(
            strategy_id="greenhouse_ats",
            target_url="https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        )
        jobs = await adapter.extract_jobs(EMPTY_RESPONSE, candidate)
        assert jobs == []

    @pytest.mark.asyncio
    async def test_extract_invalid_json(self, adapter):
        candidate = StrategyCandidate(
            strategy_id="greenhouse_ats",
            target_url="https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        )
        jobs = await adapter.extract_jobs(INVALID_JSON, candidate)
        assert jobs == []

    @pytest.mark.asyncio
    async def test_extract_malformed_response(self, adapter):
        candidate = StrategyCandidate(
            strategy_id="greenhouse_ats",
            target_url="https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        )
        jobs = await adapter.extract_jobs(MALFORMED_RESPONSE, candidate)
        assert jobs == []

    @pytest.mark.asyncio
    async def test_partial_jobs_skips_invalid(self, adapter):
        """Malformed individual job entries should be skipped, not crash."""
        candidate = StrategyCandidate(
            strategy_id="greenhouse_ats",
            target_url="https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        )
        jobs = await adapter.extract_jobs(PARTIAL_JOBS_RESPONSE, candidate)
        assert len(jobs) == 1
        assert jobs[0].title == "Good Job"


# ─── Execution Tests (Mocked HTTP) ─────────────────────────────────────────

class TestGreenhouseExecution:

    @pytest.mark.asyncio
    async def test_execute_success(self, adapter):
        candidate = StrategyCandidate(
            strategy_id="greenhouse_ats",
            adapter_id="greenhouse_ats",
            target_url="https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
            validated_url="https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
            state=CandidateState.VALIDATED,
        )
        mock_client = mock.AsyncMock(spec=SafeHTTPClient)
        mock_client.get = mock.AsyncMock(return_value=SAMPLE_GREENHOUSE_RESPONSE)

        result = await adapter.execute(candidate, mock_client)
        assert result.success is True
        assert result.jobs_discovered == 2
        assert len(result.raw_jobs) == 2
        assert result.requests_attempted == 1
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_network_failure(self, adapter):
        candidate = StrategyCandidate(
            strategy_id="greenhouse_ats",
            target_url="https://boards-api.greenhouse.io/v1/boards/acme/jobs",
            validated_url="https://boards-api.greenhouse.io/v1/boards/acme/jobs",
            state=CandidateState.VALIDATED,
        )
        mock_client = mock.AsyncMock(spec=SafeHTTPClient)
        mock_client.get = mock.AsyncMock(side_effect=ConnectionError("Network down"))

        result = await adapter.execute(candidate, mock_client)
        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0].error_type.value == "NETWORK_FAILURE"

    @pytest.mark.asyncio
    async def test_execute_parse_failure(self, adapter):
        candidate = StrategyCandidate(
            strategy_id="greenhouse_ats",
            target_url="https://boards-api.greenhouse.io/v1/boards/acme/jobs",
            validated_url="https://boards-api.greenhouse.io/v1/boards/acme/jobs",
            state=CandidateState.VALIDATED,
        )
        mock_client = mock.AsyncMock(spec=SafeHTTPClient)
        mock_client.get = mock.AsyncMock(return_value=INVALID_JSON)

        # Parse failure returns empty jobs, not a crash
        result = await adapter.execute(candidate, mock_client)
        assert result.success is True  # No exception, just 0 jobs
        assert result.jobs_discovered == 0


# ─── Integration Test ──────────────────────────────────────────────────────

class TestGreenhouseIntegration:

    @pytest.mark.asyncio
    async def test_full_pipeline_with_mocked_http(self):
        """
        End-to-end: input URL → candidate → validation → execution → RawJob
        All with mocked DNS and mocked HTTP.
        """
        adapter = GreenhouseAdapter()
        reg = StrategyRegistry()
        reg.register(adapter)
        pipeline = CandidatePipeline(registry=reg)

        # 1. Generate candidates
        candidates = reg.find_candidates("https://boards.greenhouse.io/acme")
        assert len(candidates) == 1
        assert candidates[0].state == CandidateState.DISCOVERED

        # 2. Validate (mock DNS)
        with mock.patch("app.core.security._original_getaddrinfo", return_value=[
            (2, 1, 6, "", ("93.184.216.34", 0))
        ]):
            validated, rejected = pipeline.validate_candidates(candidates)
        assert len(validated) == 1
        assert validated[0].state == CandidateState.VALIDATED

        # 3. Execute (mock HTTP)
        with mock.patch.object(SafeHTTPClient, "get", return_value=SAMPLE_GREENHOUSE_RESPONSE), \
             mock.patch.object(SafeHTTPClient, "__aenter__", return_value=mock.AsyncMock(get=mock.AsyncMock(return_value=SAMPLE_GREENHOUSE_RESPONSE))), \
             mock.patch.object(SafeHTTPClient, "__aexit__", return_value=None):

            # Patch the context manager to return a client with mocked get
            mock_client = mock.AsyncMock(spec=SafeHTTPClient)
            mock_client.get = mock.AsyncMock(return_value=SAMPLE_GREENHOUSE_RESPONSE)

            with mock.patch("app.discovery.pipeline.SafeHTTPClient") as MockHTTPClass:
                mock_ctx = mock.AsyncMock()
                mock_ctx.__aenter__ = mock.AsyncMock(return_value=mock_client)
                mock_ctx.__aexit__ = mock.AsyncMock(return_value=None)
                MockHTTPClass.return_value = mock_ctx

                result = await pipeline.execute_candidate(validated[0])

        assert result.success is True
        assert result.jobs_discovered == 2
        assert result.raw_jobs[0].provenance.provider_name == "Greenhouse"
        assert result.raw_jobs[0].provenance.strategy_id == "greenhouse_ats"


# ─── Lever Tests ───────────────────────────────────────────────────────────

from app.discovery.adapters.lever import LeverAdapter

@pytest.fixture
def lever_adapter():
    return LeverAdapter()

SAMPLE_LEVER_RESPONSE = json.dumps([
    {
        "id": "lever123",
        "text": "Senior Engineer",
        "categories": {
            "location": "San Francisco",
            "department": "Engineering",
            "commitment": "Full-Time",
            "team": "Backend"
        },
        "descriptionPlain": "Build stuff",
        "hostedUrl": "https://jobs.lever.co/acme/lever123",
        "workplaceType": "remote",
        "lists": [{"text": "Requirements", "content": "Code"}]
    },
    {
        "id": "lever456",
        "text": "Designer",
        "categories": {
            "location": "New York",
            "commitment": "Contract"
        },
        "hostedUrl": "https://jobs.lever.co/acme/lever456"
    }
]).encode("utf-8")

class TestLeverAdapter:

    def test_recognizes_url(self, lever_adapter):
        assert lever_adapter.recognizes_url("https://jobs.lever.co/netflix")
        assert lever_adapter.recognizes_url("http://jobs.lever.co/netflix/some-job")
        assert not lever_adapter.recognizes_url("https://boards.greenhouse.io/acme")

    def test_generate_candidates_with_source(self, lever_adapter):
        from app.schemas.discovery import SourceConfig
        source = SourceConfig(
            source_id="lever:acme",
            company="Acme",
            domain="acme.com",
            identifier="acme_token"
        )
        candidates = lever_adapter.generate_candidates(source=source)
        assert len(candidates) == 1
        assert candidates[0].target_url == "https://api.lever.co/v0/postings/acme_token?mode=json"
        assert candidates[0].confidence == 1.0

    @pytest.mark.asyncio
    async def test_extract_jobs_multiple(self, lever_adapter):
        candidate = StrategyCandidate(
            strategy_id="lever_ats",
            target_url="https://api.lever.co/v0/postings/acme?mode=json"
        )
        jobs = await lever_adapter.extract_jobs(SAMPLE_LEVER_RESPONSE, candidate)
        
        assert len(jobs) == 2
        
        # Verify job 1
        assert jobs[0].title == "Senior Engineer"
        assert jobs[0].company == "acme"
        assert jobs[0].location == "San Francisco"
        assert jobs[0].employment_type == "Full-Time"
        assert jobs[0].remote_status == "Remote"
        assert jobs[0].description == "Build stuff"
        assert jobs[0].provenance.source_job_id == "lever123"
        assert jobs[0].provenance.apply_url == "https://jobs.lever.co/acme/lever123"
        
        # Verify job 2
        assert jobs[1].title == "Designer"
        assert jobs[1].provenance.source_job_id == "lever456"
        assert jobs[1].provenance.apply_url == "https://jobs.lever.co/acme/lever456"
        
        # Verify uniqueness
        assert jobs[0].provenance.source_job_id != jobs[1].provenance.source_job_id
        assert jobs[0].provenance.apply_url != jobs[1].provenance.apply_url
        
    @pytest.mark.asyncio
    async def test_extract_jobs_malformed(self, lever_adapter):
        candidate = StrategyCandidate(strategy_id="lever_ats", target_url="https://api.lever.co")
        
        # Invalid JSON
        jobs = await lever_adapter.extract_jobs(b"invalid", candidate)
        assert jobs == []
        
        # Not a list
        jobs = await lever_adapter.extract_jobs(b'{"id":"1"}', candidate)
        assert jobs == []
        
        # Missing ID
        missing_id = json.dumps([{"text": "Job without ID"}]).encode("utf-8")
        jobs = await lever_adapter.extract_jobs(missing_id, candidate)
        assert jobs == []

# ─── Ashby Tests ───────────────────────────────────────────────────────────

from app.discovery.adapters.ashby import AshbyAdapter

@pytest.fixture
def ashby_adapter():
    return AshbyAdapter()

SAMPLE_ASHBY_RESPONSE = b"""
<html>
    <head></head>
    <body>
        <script id="__NEXT_DATA__" type="application/json">
        {
            "props": {
                "pageProps": {
                    "jobBoard": {
                        "jobPostings": [
                            {
                                "id": "ashby123",
                                "title": "Data Scientist",
                                "locationName": "London",
                                "jobPageUrl": "https://jobs.ashbyhq.com/acme/ashby123",
                                "descriptionHtml": "<p>Analyze data</p>",
                                "employmentType": "Full-Time",
                                "isRemote": true,
                                "departmentName": "Data",
                                "secondaryLocations": [{"name": "Paris"}],
                                "compensationTier": {"min": 100}
                            },
                            {
                                "id": "ashby456",
                                "title": "Frontend Dev",
                                "locationName": "Berlin",
                                "jobPageUrl": "https://jobs.ashbyhq.com/acme/ashby456"
                            }
                        ]
                    }
                }
            }
        }
        </script>
    </body>
</html>
"""

class TestAshbyAdapter:

    def test_recognizes_url(self, ashby_adapter):
        assert ashby_adapter.recognizes_url("https://jobs.ashbyhq.com/acme")
        assert ashby_adapter.recognizes_url("http://jobs.ashbyhq.com/acme/jobs/123")
        assert not ashby_adapter.recognizes_url("https://jobs.lever.co/acme")

    def test_generate_candidates_with_source(self, ashby_adapter):
        from app.schemas.discovery import SourceConfig
        source = SourceConfig(
            source_id="ashby:acme",
            company="Acme",
            domain="acme.com",
            identifier="acme_token"
        )
        candidates = ashby_adapter.generate_candidates(source=source)
        assert len(candidates) == 1
        assert candidates[0].target_url == "https://jobs.ashbyhq.com/acme_token"
        assert candidates[0].confidence == 1.0

    @pytest.mark.asyncio
    async def test_extract_jobs_multiple(self, ashby_adapter):
        candidate = StrategyCandidate(
            strategy_id="ashby_ats",
            target_url="https://jobs.ashbyhq.com/acme"
        )
        jobs = await ashby_adapter.extract_jobs(SAMPLE_ASHBY_RESPONSE, candidate)
        
        assert len(jobs) == 2
        
        # Verify job 1
        assert jobs[0].title == "Data Scientist"
        assert jobs[0].company == "acme"
        assert jobs[0].location == "London"
        assert jobs[0].employment_type == "Full-Time"
        assert jobs[0].remote_status == "Remote"
        assert jobs[0].description == "<p>Analyze data</p>"
        assert jobs[0].provenance.source_job_id == "ashby123"
        assert jobs[0].provenance.apply_url == "https://jobs.ashbyhq.com/acme/ashby123"
        
        # Verify job 2
        assert jobs[1].title == "Frontend Dev"
        assert jobs[1].provenance.source_job_id == "ashby456"
        assert jobs[1].provenance.apply_url == "https://jobs.ashbyhq.com/acme/ashby456"
        
        # Verify uniqueness
        assert jobs[0].provenance.source_job_id != jobs[1].provenance.source_job_id
        assert jobs[0].provenance.apply_url != jobs[1].provenance.apply_url
        
    @pytest.mark.asyncio
    async def test_extract_jobs_malformed(self, ashby_adapter):
        candidate = StrategyCandidate(strategy_id="ashby_ats", target_url="https://jobs.ashbyhq.com")
        
        # No Next data
        jobs = await ashby_adapter.extract_jobs(b"<html>no data</html>", candidate)
        assert jobs == []
        
        # Invalid JSON inside Next data
        bad_json = b'<script id="__NEXT_DATA__" type="application/json">invalid</script>'
        jobs = await ashby_adapter.extract_jobs(bad_json, candidate)
        assert jobs == []


# ─── Workable Tests ────────────────────────────────────────────────────────

from app.discovery.adapters.workable import WorkableAdapter

@pytest.fixture
def workable_adapter():
    return WorkableAdapter()

SAMPLE_WORKABLE_RESPONSE = json.dumps({
    "results": [
        {
            "id": "abc123work",
            "shortcode": "CODE123",
            "title": "Backend Developer",
            "location": {"city": "Remote", "country": "US"},
            "telecommuting": True,
            "type": "Full-Time",
            "description": "Develop backend systems.",
            "department": ["Engineering"],
            "salary": {"min": 150000}
        },
        {
            "id": "xyz987work",
            "shortcode": "CODE987",
            "title": "QA Engineer",
            "location": {"city": "Boston"},
            "telecommuting": False,
            "type": "Contract"
        }
    ]
}).encode("utf-8")

class TestWorkableAdapter:

    def test_recognizes_url(self, workable_adapter):
        assert workable_adapter.recognizes_url("https://apply.workable.com/acme")
        assert workable_adapter.recognizes_url("http://workable.com/acme/jobs/123")
        assert not workable_adapter.recognizes_url("https://jobs.lever.co/acme")

    def test_generate_candidates_with_source(self, workable_adapter):
        from app.schemas.discovery import SourceConfig
        source = SourceConfig(
            source_id="workable:acme",
            company="Acme",
            domain="acme.com",
            identifier="acme_token"
        )
        candidates = workable_adapter.generate_candidates(source=source)
        assert len(candidates) == 1
        assert candidates[0].target_url == "https://apply.workable.com/api/v3/accounts/acme_token/jobs"
        assert candidates[0].confidence == 1.0

    @pytest.mark.asyncio
    async def test_extract_jobs_multiple(self, workable_adapter):
        candidate = StrategyCandidate(
            strategy_id="workable_ats",
            target_url="https://apply.workable.com/api/v3/accounts/acme/jobs"
        )
        jobs = await workable_adapter.extract_jobs(SAMPLE_WORKABLE_RESPONSE, candidate)
        
        assert len(jobs) == 2
        
        # Verify job 1
        assert jobs[0].title == "Backend Developer"
        assert jobs[0].company == "acme"
        assert jobs[0].location == "Remote"
        assert jobs[0].employment_type == "Full-Time"
        assert jobs[0].remote_status == "Remote"
        assert jobs[0].description == "Develop backend systems."
        assert jobs[0].provenance.source_job_id == "abc123work"
        assert jobs[0].provenance.apply_url == "https://apply.workable.com/acme/j/CODE123"
        
        # Verify job 2
        assert jobs[1].title == "QA Engineer"
        assert jobs[1].provenance.source_job_id == "xyz987work"
        assert jobs[1].provenance.apply_url == "https://apply.workable.com/acme/j/CODE987"
        
        # Verify uniqueness
        assert jobs[0].provenance.source_job_id != jobs[1].provenance.source_job_id
        assert jobs[0].provenance.apply_url != jobs[1].provenance.apply_url
        
    @pytest.mark.asyncio
    async def test_extract_jobs_malformed(self, workable_adapter):
        candidate = StrategyCandidate(strategy_id="workable_ats", target_url="https://apply.workable.com")
        
        # Invalid JSON
        jobs = await workable_adapter.extract_jobs(b"invalid", candidate)
        assert jobs == []
        
        # Missing ID/shortcode
        missing_id = json.dumps({"results": [{"title": "Job without ID"}]}).encode("utf-8")
        jobs = await workable_adapter.extract_jobs(missing_id, candidate)
        assert jobs == []



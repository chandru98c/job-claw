"""
Tests for bounded RawJob schema and StrategyCandidate validation.
"""
import pytest
import json
from app.schemas.discovery import (
    RawJob,
    DiscoveryProvenanceDTO,
    StrategyCandidate,
    CandidateState,
    MAX_TITLE_LEN,
    MAX_COMPANY_LEN,
    MAX_DESCRIPTION_LEN,
    MAX_METADATA_BYTES,
)


def _make_provenance(**overrides):
    defaults = {
        "strategy_id": "test_strategy",
        "source_type": "direct_ats",
        "source_url": "https://example.com/jobs",
    }
    defaults.update(overrides)
    return DiscoveryProvenanceDTO(**defaults)


class TestRawJobBounds:

    def test_valid_raw_job(self):
        job = RawJob(
            provenance=_make_provenance(),
            title="Software Engineer",
            company="Acme Corp",
            location="San Francisco, CA",
            description="Build great software.",
        )
        assert job.title == "Software Engineer"
        assert job.company == "Acme Corp"

    def test_title_exceeds_max_length(self):
        with pytest.raises(Exception):
            RawJob(
                provenance=_make_provenance(),
                title="x" * (MAX_TITLE_LEN + 1),
                company="Acme Corp",
            )

    def test_company_exceeds_max_length(self):
        with pytest.raises(Exception):
            RawJob(
                provenance=_make_provenance(),
                title="Engineer",
                company="x" * (MAX_COMPANY_LEN + 1),
            )

    def test_description_exceeds_max_length(self):
        with pytest.raises(Exception):
            RawJob(
                provenance=_make_provenance(),
                title="Engineer",
                company="Acme",
                description="x" * (MAX_DESCRIPTION_LEN + 1),
            )

    def test_metadata_within_bounds(self):
        small_meta = {"key": "value", "number": 42}
        job = RawJob(
            provenance=_make_provenance(),
            title="Engineer",
            company="Acme",
            provider_metadata=small_meta,
        )
        assert job.provider_metadata == small_meta

    def test_metadata_exceeds_max_size(self):
        # Create metadata that exceeds MAX_METADATA_BYTES when serialized
        huge_meta = {"data": "x" * MAX_METADATA_BYTES}
        with pytest.raises(Exception) as exc_info:
            RawJob(
                provenance=_make_provenance(),
                title="Engineer",
                company="Acme",
                provider_metadata=huge_meta,
            )
        assert "maximum serialized size" in str(exc_info.value).lower() or "provider_metadata" in str(exc_info.value).lower()

    def test_provenance_required(self):
        with pytest.raises(Exception):
            RawJob(title="Engineer", company="Acme")

    def test_provenance_fields(self):
        prov = _make_provenance(
            adapter_id="greenhouse_ats",
            source_job_id="12345",
            apply_url="https://example.com/apply/12345",
            provider_name="Greenhouse",
        )
        assert prov.strategy_id == "test_strategy"
        assert prov.adapter_id == "greenhouse_ats"
        assert prov.source_job_id == "12345"
        assert prov.discovered_at is not None


class TestStrategyCandidateState:

    def test_default_state_is_discovered(self):
        c = StrategyCandidate(
            strategy_id="test",
            target_url="https://example.com",
        )
        assert c.state == CandidateState.DISCOVERED

    def test_validated_url_not_set_by_default(self):
        c = StrategyCandidate(
            strategy_id="test",
            target_url="https://example.com",
        )
        assert c.validated_url is None
        assert c.safe_ip is None

    def test_url_max_length(self):
        with pytest.raises(Exception):
            StrategyCandidate(
                strategy_id="test",
                target_url="https://example.com/" + "x" * 2048,
            )

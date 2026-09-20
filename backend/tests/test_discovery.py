from typing import Optional
"""
Tests for StrategyRegistry, CandidatePipeline, and security enforcement.
"""
import pytest
from unittest import mock

from app.discovery.interfaces import DiscoveryStrategy, StrategyCategory
from app.discovery.registry import StrategyRegistry, RegistryError
from app.discovery.pipeline import CandidatePipeline
from app.core.http import DomainPolicy
from app.core.security import SSRFViolationError
from app.schemas.discovery import (
    StrategyCandidate,
    StrategyExecutionResult,
    CandidateState,
    SourceConfig,
    RawJob,
    DiscoveryProvenanceDTO,
)


# ─── Test Helpers ───────────────────────────────────────────────────────────

class DummyStrategy(DiscoveryStrategy):
    """A minimal concrete strategy for testing."""

    def __init__(self, sid="dummy", name="Dummy", priority=100, recognizes=None):
        self._sid = sid
        self._name = name
        self._priority = priority
        self._recognizes = recognizes or (lambda url: "dummy" in url)

    @property
    def strategy_id(self): return self._sid
    @property
    def name(self): return self._name
    @property
    def category(self): return StrategyCategory.HEURISTIC
    @property
    def priority(self): return self._priority

    def recognizes_url(self, url):
        return self._recognizes(url)

    def generate_candidates(self, url: str = None, source: Optional[SourceConfig] = None) -> list[StrategyCandidate]:
        if url and not self.recognizes_url(url):
            return []
        return [
            StrategyCandidate(
                strategy_id=self._sid,
                target_url=url or "https://example.com/jobs",
                evidence="test",
                confidence=0.5,
                priority=self._priority,
            )
        ]

    async def execute(self, candidate, http_client):
        return StrategyExecutionResult(
            strategy_id=self._sid,
            candidate_id=candidate.candidate_id,
            jobs_discovered=0,
        )


class CrashingStrategy(DiscoveryStrategy):
    """A strategy that crashes during candidate generation."""

    @property
    def strategy_id(self): return "crasher"
    @property
    def name(self): return "Crasher"
    @property
    def category(self): return StrategyCategory.HEURISTIC

    def recognizes_url(self, url):
        return True

    def generate_candidates(self, url: str = None, source: Optional[SourceConfig] = None) -> list[StrategyCandidate]:
        raise RuntimeError("I crash during generation")

    async def execute(self, candidate, http_client):
        raise RuntimeError("I crashed!")


# ─── Registry Tests ─────────────────────────────────────────────────────────

class TestStrategyRegistry:

    def test_register_and_get(self):
        reg = StrategyRegistry()
        s = DummyStrategy(sid="s1")
        reg.register(s)
        assert reg.get("s1") is s
        assert len(reg) == 1

    def test_duplicate_registration_raises(self):
        reg = StrategyRegistry()
        reg.register(DummyStrategy(sid="s1"))
        with pytest.raises(RegistryError, match="Duplicate"):
            reg.register(DummyStrategy(sid="s1"))

    def test_register_non_strategy_raises(self):
        reg = StrategyRegistry()
        with pytest.raises(TypeError):
            reg.register("not_a_strategy")

    def test_get_missing_returns_none(self):
        reg = StrategyRegistry()
        assert reg.get("nonexistent") is None

    def test_list_returns_priority_order(self):
        reg = StrategyRegistry()
        reg.register(DummyStrategy(sid="low", priority=200))
        reg.register(DummyStrategy(sid="high", priority=10))
        reg.register(DummyStrategy(sid="mid", priority=100))
        listed = reg.list()
        assert [s.strategy_id for s in listed] == ["high", "mid", "low"]

    def test_find_candidates_returns_matching(self):
        reg = StrategyRegistry()
        reg.register(DummyStrategy(sid="s1", recognizes=lambda u: "greenhouse" in u))
        reg.register(DummyStrategy(sid="s2", recognizes=lambda u: "lever" in u))

        candidates = reg.find_candidates("https://boards.greenhouse.io/acme")
        assert len(candidates) == 1
        assert candidates[0].strategy_id == "s1"

    def test_find_candidates_empty_for_unrecognized(self):
        reg = StrategyRegistry()
        reg.register(DummyStrategy(sid="s1", recognizes=lambda u: False))
        assert reg.find_candidates("https://example.com") == []

    def test_crashing_strategy_does_not_affect_others(self):
        reg = StrategyRegistry()
        reg.register(CrashingStrategy())
        reg.register(DummyStrategy(sid="safe", recognizes=lambda u: True))

        candidates = reg.find_candidates("https://example.com/dummy")
        # Only the safe strategy should have produced candidates
        assert len(candidates) == 1
        assert candidates[0].strategy_id == "safe"

    def test_contains(self):
        reg = StrategyRegistry()
        reg.register(DummyStrategy(sid="x"))
        assert "x" in reg
        assert "y" not in reg


# ─── Pipeline Security Tests ───────────────────────────────────────────────

class TestCandidatePipeline:

    def _make_pipeline(self, **policy_kwargs):
        reg = StrategyRegistry()
        reg.register(DummyStrategy(sid="dummy", recognizes=lambda u: True))
        policy = DomainPolicy(**policy_kwargs)
        return CandidatePipeline(registry=reg, domain_policy=policy)

    def test_localhost_candidate_rejected(self):
        pipeline = self._make_pipeline()
        candidate = StrategyCandidate(
            strategy_id="dummy",
            target_url="http://localhost/jobs",
        )
        result = pipeline.validate_candidate(candidate)
        assert result.state == CandidateState.REJECTED

    def test_private_ip_candidate_rejected(self):
        pipeline = self._make_pipeline()
        candidate = StrategyCandidate(
            strategy_id="dummy",
            target_url="http://192.168.1.1/jobs",
        )
        result = pipeline.validate_candidate(candidate)
        assert result.state == CandidateState.REJECTED

    def test_loopback_candidate_rejected(self):
        pipeline = self._make_pipeline()
        candidate = StrategyCandidate(
            strategy_id="dummy",
            target_url="http://127.0.0.1/jobs",
        )
        result = pipeline.validate_candidate(candidate)
        assert result.state == CandidateState.REJECTED

    def test_credential_url_rejected(self):
        pipeline = self._make_pipeline()
        candidate = StrategyCandidate(
            strategy_id="dummy",
            target_url="https://user:pass@example.com/jobs",
        )
        result = pipeline.validate_candidate(candidate)
        assert result.state == CandidateState.REJECTED

    def test_domain_policy_rejection(self):
        pipeline = self._make_pipeline(allowed_domains=["greenhouse.io"])
        candidate = StrategyCandidate(
            strategy_id="dummy",
            target_url="https://evil.com/jobs",
        )
        # Mock DNS to resolve to a public IP so UrlValidator passes
        with mock.patch("app.core.security._original_getaddrinfo", return_value=[
            (2, 1, 6, "", ("93.184.216.34", 0))
        ]):
            result = pipeline.validate_candidate(candidate)
        assert result.state == CandidateState.REJECTED

    def test_valid_candidate_validated(self):
        pipeline = self._make_pipeline()
        candidate = StrategyCandidate(
            strategy_id="dummy",
            target_url="https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        )
        with mock.patch("app.core.security._original_getaddrinfo", return_value=[
            (2, 1, 6, "", ("93.184.216.34", 0))
        ]):
            result = pipeline.validate_candidate(candidate)
        assert result.state == CandidateState.VALIDATED
        assert result.validated_url is not None
        assert result.safe_ip is not None

    def test_externally_set_validated_state_is_reset(self):
        """A candidate with state=VALIDATED from an external caller must be re-validated."""
        pipeline = self._make_pipeline()
        candidate = StrategyCandidate(
            strategy_id="dummy",
            target_url="http://localhost/evil",
            state=CandidateState.VALIDATED,  # attacker tries to bypass
        )
        result = pipeline.validate_candidate(candidate)
        # Pipeline must force re-validation → localhost should be REJECTED
        assert result.state == CandidateState.REJECTED

    @pytest.mark.asyncio
    async def test_unvalidated_candidate_cannot_execute(self):
        pipeline = self._make_pipeline()
        candidate = StrategyCandidate(
            strategy_id="dummy",
            target_url="https://example.com/jobs",
            state=CandidateState.DISCOVERED,  # NOT validated
        )
        result = await pipeline.execute_candidate(candidate)
        assert result.success is False
        assert any(e.error_type.value == "VALIDATION_FAILURE" for e in result.errors)

    @pytest.mark.asyncio
    async def test_missing_strategy_returns_error(self):
        reg = StrategyRegistry()
        pipeline = CandidatePipeline(registry=reg)
        candidate = StrategyCandidate(
            strategy_id="nonexistent",
            target_url="https://example.com/jobs",
            state=CandidateState.VALIDATED,
            validated_url="https://example.com/jobs",
            safe_ip="93.184.216.34",
        )
        result = await pipeline.execute_candidate(candidate)
        assert result.success is False
        assert any(e.error_type.value == "STRATEGY_UNAVAILABLE" for e in result.errors)

    def test_validate_candidates_batch(self):
        pipeline = self._make_pipeline()
        candidates = [
            StrategyCandidate(strategy_id="dummy", target_url="http://localhost/bad"),
            StrategyCandidate(strategy_id="dummy", target_url="https://boards-api.greenhouse.io/v1/boards/acme/jobs"),
        ]
        with mock.patch("app.core.security._original_getaddrinfo", return_value=[
            (2, 1, 6, "", ("93.184.216.34", 0))
        ]):
            validated, rejected = pipeline.validate_candidates(candidates)
        assert len(rejected) == 1
        assert len(validated) == 1
        assert validated[0].state == CandidateState.VALIDATED
        assert rejected[0].state == CandidateState.REJECTED

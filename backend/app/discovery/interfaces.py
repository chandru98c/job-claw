"""
Abstract interfaces for Discovery Strategies and ATS Adapters.

These define the contracts that concrete strategies/adapters must implement.
The CandidatePipeline owns security validation — strategies receive
already-validated candidates and an approved SafeHTTPClient.

Separation of concerns:
  - Recognition:        Does this strategy apply to the given URL/context?
  - Candidate generation: What specific URLs should be probed?
  - Validation:          (Pipeline, NOT strategy) UrlValidator + DomainPolicy
  - Execution:           Fetch data via the injected SafeHTTPClient
  - Extraction:          Parse the response into RawJob objects
"""
from abc import ABC, abstractmethod
from typing import Optional
from enum import Enum

from app.schemas.discovery import (
    StrategyCandidate,
    StrategyExecutionResult,
    RawJob,
    CandidateState,
)
from app.core.http import SafeHTTPClient


class StrategyCategory(str, Enum):
    """Categories of discovery strategies."""
    ATS_ADAPTER = "ATS_ADAPTER"
    SITEMAP = "SITEMAP"
    AGGREGATOR = "AGGREGATOR"
    BROWSER = "BROWSER"
    HEURISTIC = "HEURISTIC"
    LLM_ROUTED = "LLM_ROUTED"


class DiscoveryStrategy(ABC):
    """
    Base interface for all discovery strategies.

    Strategies must NOT:
      - instantiate their own HTTP clients
      - bypass UrlValidator or DomainPolicy
      - perform security validation (that's the pipeline's job)

    Strategies receive:
      - an already-validated StrategyCandidate (state == VALIDATED)
      - an approved SafeHTTPClient instance
    """

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Stable, unique identifier for this strategy (e.g. 'greenhouse_ats')."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name (e.g. 'Greenhouse ATS Adapter')."""
        ...

    @property
    @abstractmethod
    def category(self) -> StrategyCategory:
        """The category this strategy belongs to."""
        ...

    @property
    def priority(self) -> int:
        """Lower number = higher priority. Default 100."""
        return 100

    @property
    def capabilities(self) -> dict:
        """
        Capability metadata dictionary describing what this strategy can do.
        Example: {"supports_pagination": True, "max_pages": 10}
        """
        return {}

    @abstractmethod
    def recognizes_url(self, url: str) -> bool:
        """
        Returns True if this strategy can potentially handle the given URL.
        This is a fast, synchronous check — no network access.
        Used by the registry to generate candidates.
        """
        ...

    @abstractmethod
    def generate_candidates(self, url: str) -> list[StrategyCandidate]:
        """
        Given a URL that this strategy recognizes, produce one or more
        StrategyCandidate objects in DISCOVERED state.

        These candidates are NOT validated yet — the CandidatePipeline
        will validate them before execution.

        Must NOT make network requests.
        Must NOT set candidate.state to VALIDATED.
        """
        ...

    @abstractmethod
    async def execute(
        self,
        candidate: StrategyCandidate,
        http_client: SafeHTTPClient,
    ) -> StrategyExecutionResult:
        """
        Execute the strategy for a VALIDATED candidate using the provided client.

        PRE-CONDITIONS (enforced by pipeline, NOT by strategy):
          - candidate.state == CandidateState.VALIDATED
          - candidate.validated_url is set
          - http_client is an approved SafeHTTPClient

        Returns a StrategyExecutionResult containing RawJob objects or errors.
        Must NOT crash on network/parse errors — return structured failures.
        """
        ...


class ATSAdapter(DiscoveryStrategy):
    """
    Specialised interface for ATS (Applicant Tracking System) adapters.

    ATS adapters extend DiscoveryStrategy with additional methods for
    ATS-specific URL recognition and job extraction.
    """

    @property
    def category(self) -> StrategyCategory:
        return StrategyCategory.ATS_ADAPTER

    @property
    @abstractmethod
    def ats_name(self) -> str:
        """The name of the ATS provider (e.g. 'Greenhouse', 'Lever')."""
        ...

    @abstractmethod
    def extract_board_identifier(self, url: str) -> Optional[str]:
        """
        Extract the board/company identifier from a recognized URL.
        Returns None if the URL does not contain a valid board identifier.
        """
        ...

    @abstractmethod
    async def extract_jobs(
        self,
        response_data: bytes,
        candidate: StrategyCandidate,
    ) -> list[RawJob]:
        """
        Parse raw response data from this ATS into RawJob objects.
        Must handle malformed data gracefully — return empty list, not crash.
        """
        ...

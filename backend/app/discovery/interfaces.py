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
    SourceConfig,
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
        
    def can_handle(self, source: SourceConfig) -> bool:
        """
        Returns True if this strategy can explicitly handle the given Source configuration.
        """
        return False

    @abstractmethod
    def generate_candidates(self, url: str = None, source: Optional[SourceConfig] = None) -> list[StrategyCandidate]:
        """
        Given a URL or a SourceConfig that this strategy recognizes, produce one or more
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
        
    def resolve_board_identifier(self, url: Optional[str] = None, source: Optional[SourceConfig] = None) -> Optional[str]:
        """
        Robustly resolves the board identifier from source config or URL signals.
        """
        if source and source.identifier:
            return source.identifier
        if url:
            token = self.extract_board_identifier(url)
            if token:
                return token
        if source and source.careers_url:
            token = self.extract_board_identifier(source.careers_url)
            if token:
                return token
        if source and source.domain:
            token = self.extract_board_identifier(source.domain)
            if token:
                return token

        # If source ats_type matches this ATS adapter, try extracting clean slug from domain or careers_url
        if source and source.ats_type and source.ats_type.lower() == self.ats_name.lower():
            for s in [source.careers_url, source.domain, url]:
                if not s:
                    continue
                clean = s.strip().rstrip("/")
                if "/" in clean:
                    last = clean.split("/")[-1].split("?")[0].strip()
                    if last and len(last) >= 2 and last.lower() not in ["jobs", "careers", "career", "apply"]:
                        return last
                if "." in clean:
                    sub = clean.split("//")[-1].split(".")[0].strip()
                    if sub and len(sub) >= 2 and sub.lower() not in ["jobs", "careers", "career", "apply", "www"]:
                        return sub

        return None

    def can_handle(self, source: SourceConfig) -> bool:
        """
        ATS Adapters generally handle sources where ats_type matches ats_name.
        """
        return bool(source.ats_type and source.ats_type.lower() == self.ats_name.lower())

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

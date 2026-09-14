from __future__ import annotations

"""
Strategy Registry: a typed, deterministic, declarative registry.

The registry:
  - registers strategies (with duplicate ID protection)
  - exposes capabilities
  - matches strategies to URLs
  - generates candidates
  - orders candidates deterministically by priority

The registry does NOT:
  - make network requests
  - bypass UrlValidator
  - execute strategies
  - dynamically import arbitrary Python modules
  - accept user-controlled import paths
"""
import logging
from typing import Optional

from app.discovery.interfaces import DiscoveryStrategy
from app.schemas.discovery import StrategyCandidate

logger = logging.getLogger(__name__)


class RegistryError(Exception):
    """Raised for registry-level errors (e.g. duplicate registration)."""
    pass


class StrategyRegistry:
    """
    Central, typed registry for discovery strategies.
    Strategies are registered explicitly at application startup.
    """

    def __init__(self):
        self._strategies: dict[str, DiscoveryStrategy] = {}

    def register(self, strategy: DiscoveryStrategy) -> None:
        """
        Register a strategy. Raises RegistryError on duplicate IDs.
        """
        if not isinstance(strategy, DiscoveryStrategy):
            raise TypeError(f"Expected DiscoveryStrategy, got {type(strategy).__name__}")

        sid = strategy.strategy_id
        if sid in self._strategies:
            raise RegistryError(
                f"Duplicate strategy registration: '{sid}' is already registered"
            )
        self._strategies[sid] = strategy
        logger.info(f"Registered strategy: {sid} ({strategy.name})")

    def get(self, strategy_id: str) -> Optional[DiscoveryStrategy]:
        """Fetch a specific strategy by ID. Returns None if not found."""
        return self._strategies.get(strategy_id)

    def list(self) -> list[DiscoveryStrategy]:
        """Return all strategies ordered by priority (lower = higher priority)."""
        return sorted(self._strategies.values(), key=lambda s: s.priority)

    def find_candidates(self, url: str) -> list[StrategyCandidate]:
        """
        Evaluate a URL against all registered strategies and collect candidates.

        Candidates are returned in DISCOVERED state — they are NOT validated.
        The CandidatePipeline must validate them before execution.

        One failed strategy does NOT affect others.
        """
        candidates: list[StrategyCandidate] = []

        for strategy in self.list():
            try:
                if strategy.recognizes_url(url):
                    generated = strategy.generate_candidates(url)
                    candidates.extend(generated)
            except Exception as e:
                # One strategy failure must never crash the entire registry
                logger.warning(
                    f"Strategy '{strategy.strategy_id}' failed during candidate "
                    f"generation for '{url}': {e}"
                )
                continue

        # Sort by priority (lower number = higher priority)
        candidates.sort(key=lambda c: c.priority)
        return candidates

    def __len__(self) -> int:
        return len(self._strategies)

    def __contains__(self, strategy_id: str) -> bool:
        return strategy_id in self._strategies

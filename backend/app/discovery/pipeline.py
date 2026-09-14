"""
CandidatePipeline: the non-negotiable security boundary.

Flow:
  Untrusted Input URL
        ↓
  URL normalization
        ↓
  Candidate generation (via StrategyRegistry)
        ↓
  UrlValidator
        ↓
  DomainPolicy
        ↓
  Validated / executable candidate (state=VALIDATED)
        ↓
  Selected Strategy.execute()
        ↓
  SafeHTTPClient
        ↓
  RawJob

CRITICAL INVARIANTS:
  - `state=VALIDATED` can ONLY be set by this pipeline, never by external callers.
  - An unvalidated candidate can NEVER reach a strategy's execute() method.
  - Every candidate URL passes through UrlValidator + DomainPolicy.
  - Strategies receive an approved SafeHTTPClient — they never create their own.
"""
import logging
from typing import Optional

from app.core.security import UrlValidator, SSRFViolationError
from app.core.http import SafeHTTPClient, DomainPolicy, PolicyViolationError
from app.discovery.registry import StrategyRegistry
from app.schemas.discovery import (
    StrategyCandidate,
    StrategyExecutionResult,
    DiscoveryError,
    DiscoveryErrorType,
    CandidateState,
)

logger = logging.getLogger(__name__)


class CandidatePipeline:
    """
    Owns the security validation lifecycle for discovery candidates.

    The pipeline:
      1. Takes an untrusted input URL
      2. Asks the StrategyRegistry for candidates (DISCOVERED state)
      3. Validates each candidate through UrlValidator + DomainPolicy
      4. Transitions valid candidates to VALIDATED state
      5. Executes validated candidates through their strategy with SafeHTTPClient
    """

    def __init__(
        self,
        registry: StrategyRegistry,
        domain_policy: Optional[DomainPolicy] = None,
    ):
        self._registry = registry
        self._domain_policy = domain_policy or DomainPolicy()

    def validate_candidate(
        self,
        candidate: StrategyCandidate,
    ) -> StrategyCandidate:
        """
        Validate a single candidate through the security pipeline.

        Forces candidate.state to DISCOVERED first (never trusts external state),
        then validates and transitions to VALIDATED or REJECTED.
        """
        # NEVER trust externally-supplied validation state
        candidate.state = CandidateState.DISCOVERED

        try:
            # 1. UrlValidator: SSRF, scheme, credentials, DNS resolution
            validated_url, safe_ip = UrlValidator.validate_and_resolve(candidate.target_url)

            # 2. DomainPolicy: allowed domains check
            if self._domain_policy.allowed_domains:
                import urllib.parse
                parsed = urllib.parse.urlparse(validated_url)
                host = parsed.hostname or ""
                if not any(
                    host == d or host.endswith(f".{d}")
                    for d in self._domain_policy.allowed_domains
                ):
                    raise PolicyViolationError(
                        f"Domain '{host}' is not in the allowed domain list"
                    )

            # Validation passed
            candidate.state = CandidateState.VALIDATED
            candidate.validated_url = validated_url
            candidate.safe_ip = safe_ip
            return candidate

        except (SSRFViolationError, PolicyViolationError) as e:
            candidate.state = CandidateState.REJECTED
            logger.warning(
                f"Candidate {candidate.candidate_id} rejected: {e}"
            )
            return candidate

    def validate_candidates(
        self,
        candidates: list[StrategyCandidate],
    ) -> tuple[list[StrategyCandidate], list[StrategyCandidate]]:
        """
        Validate a list of candidates. Returns (validated, rejected).
        """
        validated = []
        rejected = []
        for c in candidates:
            result = self.validate_candidate(c)
            if result.state == CandidateState.VALIDATED:
                validated.append(result)
            else:
                rejected.append(result)
        return validated, rejected

    async def execute_candidate(
        self,
        candidate: StrategyCandidate,
    ) -> StrategyExecutionResult:
        """
        Execute a single VALIDATED candidate through its strategy.

        HARD INVARIANT: refuses to execute any candidate not in VALIDATED state.
        """
        # HARD CHECK: refuse unvalidated candidates
        if candidate.state != CandidateState.VALIDATED:
            return StrategyExecutionResult(
                strategy_id=candidate.strategy_id,
                candidate_id=candidate.candidate_id,
                success=False,
                errors=[
                    DiscoveryError(
                        error_type=DiscoveryErrorType.VALIDATION_FAILURE,
                        strategy_id=candidate.strategy_id,
                        candidate_id=candidate.candidate_id,
                        message="Cannot execute an unvalidated candidate",
                    )
                ],
            )

        strategy = self._registry.get(candidate.strategy_id)
        if not strategy:
            return StrategyExecutionResult(
                strategy_id=candidate.strategy_id,
                candidate_id=candidate.candidate_id,
                success=False,
                errors=[
                    DiscoveryError(
                        error_type=DiscoveryErrorType.STRATEGY_UNAVAILABLE,
                        strategy_id=candidate.strategy_id,
                        candidate_id=candidate.candidate_id,
                        message=f"Strategy '{candidate.strategy_id}' not found in registry",
                    )
                ],
            )

        # Execute through SafeHTTPClient — strategy cannot bypass it
        try:
            async with SafeHTTPClient(policy=self._domain_policy) as http_client:
                result = await strategy.execute(candidate, http_client)
                
            # HTTP-First check: If strategy explicitly requests browser fallback
            if not result.success and result.errors:
                needs_browser = any(e.error_type == DiscoveryErrorType.REQUIRES_BROWSER_FALLBACK for e in result.errors)
                if needs_browser:
                    logger.info(f"Strategy {candidate.strategy_id} requested browser fallback for {candidate.candidate_id}")
                    from app.acquisition.browser import BrowserAcquisition
                    browser = BrowserAcquisition(domain_policy=self._domain_policy)
                    browser_result = await browser.acquire(candidate.validated_url or candidate.target_url)
                    
                    if browser_result.success and browser_result.bounded_content:
                        if hasattr(strategy, "extract_jobs"):
                            raw_jobs = await strategy.extract_jobs(browser_result.bounded_content, candidate)
                            result.success = True
                            result.raw_jobs = raw_jobs
                            result.jobs_discovered = len(raw_jobs)
                            result.errors = [e for e in result.errors if e.error_type != DiscoveryErrorType.REQUIRES_BROWSER_FALLBACK]
                        else:
                            logger.warning(f"Strategy {candidate.strategy_id} requested browser fallback but lacks extract_jobs()")
                    else:
                        logger.warning(f"Browser fallback failed for {candidate.candidate_id}: {browser_result.reason}")

            return result
        except Exception as e:
            logger.error(
                f"Strategy '{candidate.strategy_id}' crashed for candidate "
                f"{candidate.candidate_id}: {e}"
            )
            return StrategyExecutionResult(
                strategy_id=candidate.strategy_id,
                candidate_id=candidate.candidate_id,
                success=False,
                errors=[
                    DiscoveryError(
                        error_type=DiscoveryErrorType.NETWORK_FAILURE,
                        strategy_id=candidate.strategy_id,
                        candidate_id=candidate.candidate_id,
                        message=f"Strategy execution failed: {e}",
                    )
                ],
            )

    async def discover(
        self,
        input_url: str,
    ) -> list[StrategyExecutionResult]:
        """
        Full pipeline: untrusted URL → candidates → validation → execution → RawJobs.

        One failed strategy does NOT affect others.
        """
        # 1. Generate candidates from all strategies
        candidates = self._registry.find_candidates(input_url)

        if not candidates:
            return [
                StrategyExecutionResult(
                    strategy_id="pipeline",
                    candidate_id="none",
                    success=False,
                    errors=[
                        DiscoveryError(
                            error_type=DiscoveryErrorType.UNSUPPORTED_SOURCE,
                            message=f"No strategies recognized the input URL",
                        )
                    ],
                )
            ]

        # 2. Validate all candidates
        validated, rejected = self.validate_candidates(candidates)

        results: list[StrategyExecutionResult] = []

        # Report rejections as structured errors
        for r in rejected:
            results.append(
                StrategyExecutionResult(
                    strategy_id=r.strategy_id,
                    candidate_id=r.candidate_id,
                    success=False,
                    errors=[
                        DiscoveryError(
                            error_type=DiscoveryErrorType.CANDIDATE_REJECTED,
                            strategy_id=r.strategy_id,
                            candidate_id=r.candidate_id,
                            message=f"Candidate URL rejected by security pipeline",
                        )
                    ],
                )
            )

        # 3. Execute validated candidates
        for candidate in validated:
            result = await self.execute_candidate(candidate)
            results.append(result)

        return results

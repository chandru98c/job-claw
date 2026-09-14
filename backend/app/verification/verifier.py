import httpx
from datetime import datetime, timezone
import logging
from urllib.parse import urlparse

from app.core.http import SafeHTTPClient, DomainPolicy, PolicyViolationError
from app.schemas.verification import VerificationResult, VerificationOutcome, VerificationReason
from app.core.security import UrlValidator

logger = logging.getLogger(__name__)

class VerificationEngine:
    """
    Deterministically requests a source_url and classifies the response evidence
    without mutating the database.
    """
    
    @staticmethod
    async def verify_url(url: str, policy: DomainPolicy = DomainPolicy()) -> VerificationResult:
        """
        Runs the URL through the security layer and SafeHTTPClient.
        Returns a bounded VerificationResult determining the evidence of existence.
        """
        # We start by validating URL format (even though SafeHTTPClient does it, we might fail early)
        try:
            UrlValidator.validate_and_resolve(url)
        except Exception as e:
            return VerificationResult(
                outcome=VerificationOutcome.BLOCKED,
                reason=VerificationReason.BLOCKED_BY_POLICY,
                reachable=False,
                job_present=False
            )

        try:
            async with SafeHTTPClient(policy=policy) as client:
                response_bytes = await client.get(url)
                
            # If we reached here, we got a 200-level HTTP response
            content_str = response_bytes.decode('utf-8', errors='ignore').lower()
            
            # Very basic deterministic missing signal logic.
            # In a real app, this would use source-specific adapters (e.g. greenhouse adapter checks for specific "this job is closed" div)
            # The prompt explicitly forbids generic "missing text" expiry without deterministic signals.
            # So, for an arbitrary 200 OK, it is AMBIGUOUS unless we have a specific parser.
            # If a source parser was added later, it would check the exact ATS payload.
            
            # Since we cannot generically expire on missing text, a successful 200 is treated as ACTIVE_CONFIRMED 
            # if we don't have deterministic proof otherwise. 
            # (Wait, actually "200 + ambiguous content -> AMBIGUOUS". So we return AMBIGUOUS unless we can confirm the job title is on page,
            # but the prompt says: "Do NOT implement: HTTP 200 + some expected text is missing = JOB_NOT_FOUND generically. 200 + ambiguous content -> AMBIGUOUS.")
            
            return VerificationResult(
                outcome=VerificationOutcome.AMBIGUOUS,
                reason=VerificationReason.AMBIGUOUS,
                http_status=200,
                reachable=True,
                job_present=None
            )

        except PolicyViolationError as e:
            return VerificationResult(
                outcome=VerificationOutcome.BLOCKED,
                reason=VerificationReason.BLOCKED_BY_POLICY,
                reachable=False,
                job_present=None
            )
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 404:
                return VerificationResult(
                    outcome=VerificationOutcome.CONFIRMED_MISSING,
                    reason=VerificationReason.HTTP_404,
                    http_status=404,
                    reachable=True,
                    job_present=False
                )
            elif status == 410:
                return VerificationResult(
                    outcome=VerificationOutcome.CONFIRMED_MISSING,
                    reason=VerificationReason.HTTP_410,
                    http_status=410,
                    reachable=True,
                    job_present=False
                )
            elif status == 403 or status == 401:
                # Remote denial, we don't know if the job is there
                return VerificationResult(
                    outcome=VerificationOutcome.AMBIGUOUS,
                    reason=VerificationReason.AMBIGUOUS,
                    http_status=status,
                    reachable=True,
                    job_present=None
                )
            elif status == 429:
                return VerificationResult(
                    outcome=VerificationOutcome.TRANSIENT_FAILURE,
                    reason=VerificationReason.RATE_LIMITED,
                    http_status=429,
                    reachable=True,
                    job_present=None
                )
            elif status >= 500:
                return VerificationResult(
                    outcome=VerificationOutcome.TRANSIENT_FAILURE,
                    reason=VerificationReason.SERVER_ERROR,
                    http_status=status,
                    reachable=True,
                    job_present=None
                )
            else:
                return VerificationResult(
                    outcome=VerificationOutcome.AMBIGUOUS,
                    reason=VerificationReason.AMBIGUOUS,
                    http_status=status,
                    reachable=True,
                    job_present=None
                )
        except httpx.TimeoutException:
            return VerificationResult(
                outcome=VerificationOutcome.TRANSIENT_FAILURE,
                reason=VerificationReason.TIMEOUT,
                reachable=False,
                job_present=None
            )
        except httpx.RequestError:
            return VerificationResult(
                outcome=VerificationOutcome.TRANSIENT_FAILURE,
                reason=VerificationReason.NETWORK_ERROR,
                reachable=False,
                job_present=None
            )
        except Exception:
            return VerificationResult(
                outcome=VerificationOutcome.TRANSIENT_FAILURE,
                reason=VerificationReason.NETWORK_ERROR,
                reachable=False,
                job_present=None
            )

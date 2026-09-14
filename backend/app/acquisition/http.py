import logging
from typing import Optional

from app.core.http import SafeHTTPClient, DomainPolicy, PolicyViolationError
from app.core.security import SSRFViolationError
from app.acquisition.base import AcquisitionStrategy, AcquisitionResult

logger = logging.getLogger(__name__)

class HTTPAcquisition(AcquisitionStrategy):
    """
    Standard HTTP acquisition using SafeHTTPClient.
    """
    def __init__(self, domain_policy: Optional[DomainPolicy] = None):
        self.domain_policy = domain_policy or DomainPolicy()

    async def acquire(self, url: str) -> AcquisitionResult:
        try:
            async with SafeHTTPClient(policy=self.domain_policy) as client:
                content = await client.get(url)
                
                return AcquisitionResult(
                    success=True,
                    method="HTTP",
                    final_url=url, # SafeHTTPClient currently doesn't expose the final URL after redirects easily, so we return the initial one.
                    status_code=200,
                    bounded_content=content
                )
        except PolicyViolationError as e:
            logger.warning(f"HTTP Acquisition PolicyViolation for {url}: {e}")
            return AcquisitionResult(success=False, method="HTTP", reason=f"POLICY_VIOLATION: {e}")
        except SSRFViolationError as e:
            logger.warning(f"HTTP Acquisition SSRF blocked for {url}: {e}")
            return AcquisitionResult(success=False, method="HTTP", reason=f"SSRF_BLOCKED: {e}")
        except Exception as e:
            logger.warning(f"HTTP Acquisition Failed for {url}: {e}")
            return AcquisitionResult(success=False, method="HTTP", reason=f"HTTP_ERROR: {e}")

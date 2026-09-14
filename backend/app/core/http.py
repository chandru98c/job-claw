import httpx
import logging
import asyncio
from pydantic import BaseModel
from typing import Optional, Dict, Any
import urllib.parse
from app.core.security import UrlValidator, SSRFViolationError, _dns_override
import socket

logger = logging.getLogger(__name__)

class DomainPolicy(BaseModel):
    allowed_domains: Optional[list[str]] = None
    timeout_seconds: float = 10.0
    max_response_bytes: int = 5 * 1024 * 1024  # 5MB default
    max_retries: int = 2
    max_redirects: int = 5
    concurrency_limit: int = 10
    
class PolicyViolationError(Exception):
    pass

class SafeHTTPClient:
    """
    A safe HTTP client wrapper that enforces UrlValidator and DomainPolicy.
    All outbound requests from Job-Claw MUST use this client.
    """
    def __init__(self, policy: DomainPolicy = DomainPolicy()):
        self.policy = policy
        # Ensure TLS verification is explicitly ON.
        self._client = httpx.AsyncClient(verify=True, timeout=self.policy.timeout_seconds)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._client.aclose()
        
    async def get(self, url: str, headers: Optional[Dict[str, str]] = None) -> bytes:
        return await self.request("GET", url, headers=headers)

    async def request(self, method: str, url: str, **kwargs) -> bytes:
        """
        Executes an HTTP request safely.
        Validates the initial URL, streams the response to enforce size limits,
        and manually follows redirects to ensure each hop is validated against SSRF.
        """
        current_url = url
        redirects_followed = 0
        
        for attempt in range(self.policy.max_retries + 1):
            try:
                # We do our own redirect loop to validate each hop
                while redirects_followed <= self.policy.max_redirects:
                    current_url, safe_ip = UrlValidator.validate_and_resolve(current_url)

                    # 2. Domain Policy Validation
                    parsed = urllib.parse.urlparse(current_url)
                    if self.policy.allowed_domains:
                        # Allow exact match or subdomains
                        host = parsed.hostname or ""
                        if not any(host == d or host.endswith(f".{d}") for d in self.policy.allowed_domains):
                            raise PolicyViolationError(f"Domain {host} is not in the allowed list.")

                    # TOCTOU Protection: Pin the DNS resolution to the safe_ip we just validated.
                    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
                    override_token = _dns_override.set({
                        'host': parsed.hostname,
                        'result': (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (safe_ip, port))
                    })
                    
                    try:
                        # 3. Network Request (Streaming to enforce size limits)
                        # We explicitly do NOT use follow_redirects=True
                        async with self._client.stream(method, current_url, **kwargs) as response:
                            if response.status_code in (301, 302, 303, 307, 308):
                                # Handle redirect
                                location = response.headers.get("Location")
                                if not location:
                                    raise PolicyViolationError("Redirect response missing Location header")
                                
                                # Resolve relative redirects
                                current_url = urllib.parse.urljoin(current_url, location)
                                redirects_followed += 1
                                continue # Loop back to validate the new URL
                                
                            response.raise_for_status()
                            
                            # Read body enforcing size limit
                            content = bytearray()
                            async for chunk in response.aiter_bytes():
                                content.extend(chunk)
                                if len(content) > self.policy.max_response_bytes:
                                    raise PolicyViolationError(f"Response exceeded maximum allowed size of {self.policy.max_response_bytes} bytes")
                            
                            return bytes(content)
                    finally:
                        _dns_override.reset(override_token)

                raise PolicyViolationError(f"Exceeded maximum redirects ({self.policy.max_redirects})")

            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                if attempt == self.policy.max_retries:
                    raise
                # Exponential backoff
                await asyncio.sleep(2 ** attempt)
                
        raise PolicyViolationError("Max retries exceeded")

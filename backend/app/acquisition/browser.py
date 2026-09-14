import logging
import urllib.parse
from typing import Optional, List
from pydantic import BaseModel
from playwright.async_api import async_playwright, Page, Request, Response, Route, Error as PlaywrightError

from app.core.security import UrlValidator, SSRFViolationError
from app.core.http import DomainPolicy
from app.acquisition.base import AcquisitionStrategy, AcquisitionResult, NetworkCandidate

logger = logging.getLogger(__name__)

class BrowserPolicy(BaseModel):
    navigation_timeout_ms: int = 20000
    max_navigations: int = 3
    max_network_events: int = 150
    max_html_bytes: int = 5 * 1024 * 1024
    
    # Block heavy/unnecessary resources
    blocked_resource_types: List[str] = ["image", "media", "font", "stylesheet"]

class BrowserAcquisition(AcquisitionStrategy):
    """
    Playwright-based acquisition strategy. Strictly bounded and used as a fallback.
    Enforces SSRF protections on every network request.
    """
    def __init__(self, domain_policy: Optional[DomainPolicy] = None, browser_policy: Optional[BrowserPolicy] = None):
        self.domain_policy = domain_policy or DomainPolicy()
        self.browser_policy = browser_policy or BrowserPolicy()
        self._network_candidates: List[NetworkCandidate] = []
        self._navigation_count = 0

    def _check_domain(self, url: str) -> bool:
        """Check if URL matches the allowed domain policy."""
        if not self.domain_policy.allowed_domains:
            return True
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
        return any(host == d or host.endswith(f".{d}") for d in self.domain_policy.allowed_domains)

    async def _handle_route(self, route: Route, request: Request):
        """
        Intercepts EVERY request made by Playwright.
        Enforces SSRF and Domain Policies.
        """
        # Block heavy resources
        if request.resource_type in self.browser_policy.blocked_resource_types:
            await route.abort()
            return

        try:
            # 1. SSRF Protection: Must pass for ALL requests (navigations, XHR, etc)
            validated_url, safe_ip = UrlValidator.validate_and_resolve(request.url)
            
            # 2. Navigation protection: Navigations MUST match DomainPolicy
            if request.is_navigation_request():
                self._navigation_count += 1
                if self._navigation_count > self.browser_policy.max_navigations:
                    logger.warning(f"Browser exceeded max navigations ({self.browser_policy.max_navigations})")
                    await route.abort("aborted")
                    return
                
                if not self._check_domain(validated_url):
                    logger.warning(f"Browser navigation blocked by DomainPolicy: {validated_url}")
                    await route.abort("accessdenied")
                    return

            # Proceed if safe
            await route.continue_()
            
        except SSRFViolationError as e:
            logger.warning(f"Browser SSRF blocked for {request.url}: {e}")
            await route.abort("accessdenied")
        except Exception as e:
            logger.error(f"Error in route handler for {request.url}: {e}")
            await route.abort("failed")

    async def _handle_response(self, response: Response):
        """
        Observes network traffic to identify potential API candidates (e.g., ATS endpoints).
        Captures ONLY metadata.
        """
        if len(self._network_candidates) >= self.browser_policy.max_network_events:
            return

        request = response.request
        
        # Only track useful API-like requests (XHR/Fetch/Document)
        if request.resource_type in ["xhr", "fetch", "document"]:
            self._network_candidates.append(
                NetworkCandidate(
                    method=request.method,
                    url=request.url,
                    status=response.status,
                    content_type=response.headers.get("content-type"),
                    resource_type=request.resource_type
                )
            )

    async def acquire(self, url: str) -> AcquisitionResult:
        """
        Launch a bounded browser session to acquire the page HTML and observe APIs.
        """
        # Pre-validate the initial URL (fail fast)
        try:
            validated_url, _ = UrlValidator.validate_and_resolve(url)
            if not self._check_domain(validated_url):
                return AcquisitionResult(success=False, method="BROWSER", reason="POLICY_VIOLATION: Initial URL not allowed by domain policy")
        except SSRFViolationError as e:
            return AcquisitionResult(success=False, method="BROWSER", reason=f"SSRF_BLOCKED: {e}")

        # Execute bounded browser
        playwright = None
        browser = None
        context = None
        page = None
        
        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(
                ignore_https_errors=False, # Enforce TLS
                java_script_enabled=True
            )
            page = await context.new_page()
            
            # Enforce strict routing
            await page.route("**/*", self._handle_route)
            page.on("response", self._handle_response)
            
            # Navigate
            response = await page.goto(
                validated_url, 
                timeout=self.browser_policy.navigation_timeout_ms,
                wait_until="domcontentloaded"
            )
            
            if not response:
                return AcquisitionResult(success=False, method="BROWSER", reason="NO_RESPONSE")
                
            # Wait a brief moment for dynamic JS/React to render ATS lists
            try:
                await page.wait_for_timeout(3000)
            except Exception:
                pass
                
            final_url = page.url
            html_content = await page.content()
            html_bytes = html_content.encode('utf-8')
            
            if len(html_bytes) > self.browser_policy.max_html_bytes:
                logger.warning(f"Browser acquired HTML exceeded limit ({len(html_bytes)} bytes). Truncating.")
                html_bytes = html_bytes[:self.browser_policy.max_html_bytes]
                
            return AcquisitionResult(
                success=True,
                method="BROWSER",
                final_url=final_url,
                status_code=response.status,
                content_type=response.headers.get("content-type"),
                bounded_content=html_bytes,
                network_candidates=self._network_candidates
            )
            
        except PlaywrightError as e:
            logger.warning(f"Playwright acquisition failed for {url}: {e}")
            return AcquisitionResult(success=False, method="BROWSER", reason=f"BROWSER_ERROR: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during browser acquisition for {url}: {e}")
            return AcquisitionResult(success=False, method="BROWSER", reason=f"UNKNOWN_ERROR: {e}")
        finally:
            # Ensure cleanup
            if page: await page.close()
            if context: await context.close()
            if browser: await browser.close()
            if playwright: await playwright.stop()

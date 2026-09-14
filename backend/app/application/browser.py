import logging
import asyncio
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from playwright.async_api import async_playwright, Page, Request, Response, Route, Error as PlaywrightError

from app.core.security import UrlValidator, SSRFViolationError
from app.core.http import DomainPolicy
from app.acquisition.browser import BrowserPolicy

logger = logging.getLogger(__name__)

class ApplicationBrowser:
    """
    State-changing application browser.
    Enforces Phase 8 SSRF and DomainPolicy bounds.
    """
    def __init__(self, domain_policy: Optional[DomainPolicy] = None, browser_policy: Optional[BrowserPolicy] = None):
        self.domain_policy = domain_policy or DomainPolicy()
        self.browser_policy = browser_policy or BrowserPolicy()
        self._navigation_count = 0
        
    def _check_domain(self, url: str) -> bool:
        """Check if URL matches the allowed domain policy."""
        if not self.domain_policy.allowed_domains:
            return True
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
        return any(host == d or host.endswith(f".{d}") for d in self.domain_policy.allowed_domains)

    async def _handle_route(self, route: Route, request: Request):
        if request.resource_type in self.browser_policy.blocked_resource_types:
            await route.abort()
            return

        try:
            validated_url, safe_ip = UrlValidator.validate_and_resolve(request.url)
            
            if request.is_navigation_request():
                self._navigation_count += 1
                if self._navigation_count > self.browser_policy.max_navigations:
                    logger.warning("Browser exceeded max navigations")
                    await route.abort("aborted")
                    return
                
                if not self._check_domain(validated_url):
                    logger.warning(f"Browser navigation blocked by DomainPolicy: {validated_url}")
                    await route.abort("accessdenied")
                    return

            await route.continue_()
        except SSRFViolationError as e:
            logger.warning(f"Browser SSRF blocked for {request.url}: {e}")
            await route.abort("accessdenied")
        except Exception as e:
            logger.error(f"Error in route handler for {request.url}: {e}")
            await route.abort("failed")

    async def inspect_form(self, url: str) -> Dict[str, Any]:
        """Navigates to URL and extracts bounded form metadata."""
        try:
            validated_url, _ = UrlValidator.validate_and_resolve(url)
            if not self._check_domain(validated_url):
                return {"success": False, "reason": "POLICY_VIOLATION"}
        except SSRFViolationError as e:
            return {"success": False, "reason": f"SSRF_BLOCKED: {e}"}

        playwright = None
        browser = None
        context = None
        page = None
        
        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(ignore_https_errors=False, java_script_enabled=True)
            page = await context.new_page()
            
            await page.route("**/*", self._handle_route)
            
            response = await page.goto(validated_url, timeout=self.browser_policy.navigation_timeout_ms, wait_until="domcontentloaded")
            if not response:
                return {"success": False, "reason": "NO_RESPONSE"}
                
            # Extract form elements
            fields = await page.evaluate('''() => {
                const elements = document.querySelectorAll('input, select, textarea');
                const results = [];
                elements.forEach(el => {
                    if (el.type === 'hidden' || el.type === 'submit') return;
                    let label = "";
                    if (el.id) {
                        const labelEl = document.querySelector(`label[for="${el.id}"]`);
                        if (labelEl) label = labelEl.innerText;
                    }
                    if (!label && el.placeholder) label = el.placeholder;
                    if (!label && el.name) label = el.name;
                    
                    let options = null;
                    if (el.tagName.toLowerCase() === 'select') {
                        options = Array.from(el.options).map(o => o.value);
                    }
                    
                    results.push({
                        id: el.id || el.name || Math.random().toString(36).substring(7),
                        name: el.name,
                        label: label.trim(),
                        type: el.type,
                        required: el.required || false,
                        placeholder: el.placeholder || "",
                        options: options
                    });
                });
                return results;
            }''')
            
            # Limit fields extracted
            if len(fields) > 100:
                fields = fields[:100]
                
            return {"success": True, "fields": fields}
        except PlaywrightError as e:
            return {"success": False, "reason": f"BROWSER_ERROR: {e}"}
        finally:
            if page: await page.close()
            if context: await context.close()
            if browser: await browser.close()
            if playwright: await playwright.stop()

    async def submit_form(self, url: str, filled_fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Navigates to URL, fills form deterministically, and submits."""
        try:
            validated_url, _ = UrlValidator.validate_and_resolve(url)
            if not self._check_domain(validated_url):
                return {"success": False, "reason": "POLICY_VIOLATION"}
        except SSRFViolationError as e:
            return {"success": False, "reason": f"SSRF_BLOCKED: {e}"}

        playwright = None
        browser = None
        context = None
        page = None
        
        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(ignore_https_errors=False, java_script_enabled=True)
            page = await context.new_page()
            
            await page.route("**/*", self._handle_route)
            
            response = await page.goto(validated_url, timeout=self.browser_policy.navigation_timeout_ms, wait_until="domcontentloaded")
            if not response:
                return {"success": False, "reason": "NO_RESPONSE"}
                
            for field in filled_fields:
                if not field.get("value"):
                    continue
                # Determine selector
                selector = f"#{field['id']}" if field.get("id") else f"[name='{field.get('name')}']"
                
                try:
                    if field.get("type") == "file":
                        await page.set_input_files(selector, field["value"])
                    elif field.get("type") == "checkbox":
                        if field["value"] in [True, "true", "True", "on"]:
                            await page.check(selector)
                    elif field.get("type") == "radio":
                        await page.check(f"{selector}[value='{field['value']}']")
                    elif field.get("type") == "select-one":
                        await page.select_option(selector, field["value"])
                    else:
                        await page.fill(selector, str(field["value"]))
                except Exception as e:
                    logger.warning(f"Could not fill field {field.get('id')}: {e}")
            
            # Submit form and capture the response
            submit_btn = await page.query_selector("button[type='submit'], input[type='submit'], button:has-text('Submit'), button:has-text('Apply')")
            if not submit_btn:
                return {"success": False, "reason": "NO_SUBMIT_BUTTON"}

            # Capture POST response via listener
            submit_responses = []
            def on_response(response):
                if response.request.resource_type in ("document", "navigation"):
                    submit_responses.append(response)
            
            page.on("response", on_response)

            # Submit form via JavaScript to bypass HTML5 validation
            # (worker fills fields programmatically; file inputs can't be populated)
            form_exists = await page.evaluate("() => !!document.querySelector('form')")
            
            try:
                async with page.expect_navigation(timeout=15000, wait_until="domcontentloaded"):
                    if not form_exists:
                        submit_btn = await page.query_selector("button[type='submit'], input[type='submit'], button:has-text('Submit'), button:has-text('Apply')")
                        if not submit_btn:
                            return {"success": False, "reason": "NO_FORM_OR_SUBMIT_BUTTON"}
                        await submit_btn.click()
                    else:
                        await page.evaluate("() => document.querySelector('form').submit()")
            except Exception:
                pass
                
            final_url = page.url
            
            # Check HTTP status if we captured a response
            submit_response = submit_responses[-1] if submit_responses else None
            if submit_response:
                status_code = submit_response.status
                if status_code >= 400:
                    return {"success": False, "reason": f"HTTP_{status_code}", "uncertain": False}
            
            # Check page content for success confirmation
            try:
                page_text = await page.inner_text("body")
            except Exception:
                page_text = ""
            page_text_lower = page_text.lower()
            
            success_markers = ["success", "application received", "thank you", "submitted", "confirmation"]
            has_success = any(marker in page_text_lower for marker in success_markers)
            
            if has_success:
                return {"success": True, "destination": final_url}
            else:
                # 200 response but no clear success signal — uncertain
                return {"success": False, "reason": "NO_SUCCESS_CONFIRMATION", "uncertain": True}
        except PlaywrightError as e:
            # Revert to UNKNOWN status on uncertain browser errors (like navigation failures after click)
            return {"success": False, "reason": f"BROWSER_ERROR: {e}", "uncertain": True}
        finally:
            if page: await page.close()
            if context: await context.close()
            if browser: await browser.close()
            if playwright: await playwright.stop()

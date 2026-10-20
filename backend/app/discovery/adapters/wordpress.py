import json
import re
import time
import logging
import xml.etree.ElementTree as ET
from html import unescape
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

from app.discovery.interfaces import ATSAdapter
from app.schemas.discovery import (
    StrategyCandidate,
    StrategyExecutionResult,
    RawJob,
    DiscoveryProvenanceDTO,
    DiscoveryError,
    DiscoveryErrorType,
    SourceConfig,
)
from app.core.http import SafeHTTPClient
from app.discovery.utils.post_scraper import parse_wp_post_webpage

logger = logging.getLogger(__name__)


class WordPressAdapter(ATSAdapter):
    """
    Direct discovery adapter for WordPress-powered job boards and career portals.
    Combines REST API endpoints (/wp-json/wp/v2/posts) and XML sitemaps (/post-sitemap.xml),
    then performs deep post webpage extraction to extract the true direct application link
    (never the aggregator source domain) and exact location/qualification from structured tables.
    """

    @property
    def strategy_id(self) -> str:
        return "wordpress_ats"

    @property
    def name(self) -> str:
        return "WordPress Job Adapter"

    @property
    def ats_name(self) -> str:
        return "WordPress"

    @property
    def priority(self) -> int:
        return 12

    def extract_board_identifier(self, url: str) -> Optional[str]:
        if not url:
            return None
        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        host = parsed.netloc or parsed.path
        if host:
            return host.lower().replace("www.", "")
        return None

    def recognizes_url(self, url: str) -> bool:
        if not url:
            return False
        lower = url.lower()
        return "wp-json" in lower or "wordpress" in lower or "sitemap" in lower

    def can_handle(self, source: SourceConfig) -> bool:
        if not source:
            return False
        if source.ats_type and source.ats_type.lower() == "wordpress":
            return True
        if source.domain and ("optimum" in source.domain.lower() or "theoptimum" in source.domain.lower()):
            return True
        return False

    def generate_candidates(self, url: str = None, source: SourceConfig = None) -> list[StrategyCandidate]:
        source_id = source.source_id if source else None
        base_url = None

        if source and source.careers_url:
            base_url = source.careers_url.rstrip("/")
        elif url:
            base_url = url.rstrip("/")
        elif source and source.domain:
            d = source.domain.strip()
            base_url = f"https://{d}" if not d.startswith("http") else d.rstrip("/")

        if not base_url:
            return []

        # Parse base domain
        parsed = urlparse(base_url)
        origin = f"{parsed.scheme or 'https'}://{parsed.netloc}"

        candidates = [
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=f"{origin}/wp-json/wp/v2/types",
                evidence=f"WordPress dynamic custom post types discovery: {origin}",
                confidence=0.98,
                source="source_config" if source else "url_pattern_match",
                source_id=source_id,
                priority=self.priority,
            ),
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=f"{origin}/wp-json/wp/v2/posts?per_page=30",
                evidence=f"WordPress standard REST API: {origin}",
                confidence=0.95,
                source="source_config" if source else "url_pattern_match",
                source_id=source_id,
                priority=self.priority + 1,
            ),
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=f"{origin}/post-sitemap.xml",
                evidence=f"WordPress post sitemap: {origin}",
                confidence=0.90,
                source="source_config" if source else "url_pattern_match",
                source_id=source_id,
                priority=self.priority + 2,
            ),
            StrategyCandidate(
                strategy_id=self.strategy_id,
                adapter_id=self.strategy_id,
                target_url=f"{origin}/sitemap_index.xml",
                evidence=f"WordPress sitemap index: {origin}",
                confidence=0.85,
                source="source_config" if source else "url_pattern_match",
                source_id=source_id,
                priority=self.priority + 3,
            ),
        ]
        return candidates

    async def execute(
        self,
        candidate: StrategyCandidate,
        http_client: SafeHTTPClient,
    ) -> StrategyExecutionResult:
        start_time = time.monotonic()
        result = StrategyExecutionResult(
            strategy_id=self.strategy_id,
            adapter_id=self.strategy_id,
            candidate_id=candidate.candidate_id,
        )

        url = candidate.validated_url or candidate.target_url
        try:
            # Handle dynamic WordPress custom post type discovery (/types)
            if "/wp-json/wp/v2/types" in url:
                headers = {
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                }
                response_bytes = await http_client.get(url, headers=headers)
                result.requests_attempted += 1
                types_data = json.loads(response_bytes.decode("utf-8", errors="replace"))

                job_keywords = ["opportunity", "opportunities", "job", "jobs", "career", "careers", "position", "opening", "vacancy", "odc", "consulting"]
                matching_bases = []

                if isinstance(types_data, dict):
                    for type_key, type_meta in types_data.items():
                        if type_key in ["post", "page", "attachment", "nav_menu_item", "wp_block", "wp_template", "wp_template_part", "wp_global_styles", "wp_navigation"]:
                            continue
                        rest_base = type_meta.get("rest_base") or type_key
                        if any(kw in type_key.lower() or kw in rest_base.lower() for kw in job_keywords):
                            matching_bases.append(rest_base)

                parsed_origin = urlparse(url)
                origin = f"{parsed_origin.scheme}://{parsed_origin.netloc}"

                # Try preloading location taxonomy terms if available (e.g. odc_locations)
                loc_map = {}
                for tax in ["odc_locations", "locations", "job_locations"]:
                    try:
                        tax_bytes = await http_client.get(f"{origin}/wp-json/wp/v2/{tax}?per_page=100", headers=headers)
                        tax_data = json.loads(tax_bytes.decode("utf-8", errors="replace"))
                        if isinstance(tax_data, list):
                            for t in tax_data:
                                if isinstance(t, dict) and "id" in t and "name" in t:
                                    loc_map[t["id"]] = t["name"]
                    except Exception:
                        pass

                raw_jobs: List[RawJob] = []
                for base in matching_bases:
                    try:
                        ep_url = f"{origin}/wp-json/wp/v2/{base}?per_page=50"
                        ep_bytes = await http_client.get(ep_url, headers=headers)
                        result.requests_attempted += 1
                        ep_items = json.loads(ep_bytes.decode("utf-8", errors="replace"))
                        if not isinstance(ep_items, list):
                            continue

                        for item in ep_items:
                            if not isinstance(item, dict):
                                continue
                            job_link = item.get("link")
                            if not job_link:
                                continue

                            title_raw = item.get("title", {})
                            title_str = title_raw.get("rendered", "") if isinstance(title_raw, dict) else str(title_raw)
                            clean_title = unescape(re.sub(r"<[^>]+>", "", title_str)).strip()

                            content_raw = item.get("content", {})
                            content_str = content_raw.get("rendered", "") if isinstance(content_raw, dict) else str(content_raw)
                            clean_desc = unescape(re.sub(r"<[^>]+>", " ", content_str))
                            clean_desc = " ".join(clean_desc.split())[:4000]

                            # Determine company
                            company_name = "Optimum Solutions" if "optimum" in origin.lower() else parsed_origin.netloc.split(".")[0].title()

                            # Determine location
                            job_location = "India"
                            for loc_id in (item.get("odc_locations") or item.get("locations") or []):
                                if loc_id in loc_map:
                                    job_location = loc_map[loc_id]
                                    break
                            if job_location == "India" and "chennai" in clean_desc.lower():
                                job_location = "Chennai, India"
                            elif job_location == "Chennai":
                                job_location = "Chennai, India"

                            # For corporate WordPress career posts, job_link IS the exact application URL!
                            raw_jobs.append(
                                RawJob(
                                    title=clean_title or "Job Opening",
                                    company=company_name,
                                    location=job_location,
                                    description=clean_desc if clean_desc else clean_title,
                                    apply_url=job_link,
                                    url=job_link,
                                    provenance=DiscoveryProvenanceDTO(
                                        strategy_id=self.strategy_id,
                                        adapter_id=self.strategy_id,
                                        source_id=candidate.source_id,
                                        source_type="direct_ats",
                                        source_url=job_link,
                                        apply_url=job_link,
                                        provider_name=self.ats_name,
                                    ),
                                )
                            )
                    except Exception as base_err:
                        logger.debug(f"Error reading custom WordPress endpoint {base}: {base_err}")

                if raw_jobs:
                    result.raw_jobs = raw_jobs
                    result.jobs_discovered = len(raw_jobs)
                    result.success = True
                    result.duration_seconds = time.monotonic() - start_time
                    logger.info(f"WordPressAdapter extracted {len(raw_jobs)} direct jobs via custom post types from {url}")
                    return result

            is_sitemap = "sitemap" in url.lower() or url.endswith(".xml")
            headers = {
                "Accept": "application/xml,text/xml,*/*" if is_sitemap else "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            }
            response_bytes = await http_client.get(url, headers=headers)
            result.requests_attempted += 1

            post_items: List[Dict[str, Any]] = []

            if is_sitemap:
                # Parse XML sitemap
                post_items = self._parse_sitemap_urls(response_bytes, url)
            else:
                # Parse REST API posts
                post_items = self._parse_rest_api_posts(response_bytes)

            raw_jobs: List[RawJob] = []

            # Deep scrape each post webpage to extract real apply link and true location
            for item in post_items[:25]:
                post_link = item.get("link")
                if not post_link:
                    continue

                try:
                    page_bytes = await http_client.get(
                        post_link,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                            "Referer": "https://www.google.com/",
                        }
                    )
                    result.requests_attempted += 1
                    page_html = page_bytes.decode("utf-8", errors="replace")

                    details = parse_wp_post_webpage(page_html, post_link)

                    # Title & Company
                    title = details.get("title") or item.get("fallback_title") or "Job Opening"
                    company = details.get("company") or item.get("fallback_company") or "Direct Employer"

                    # Location: Structured table location is preferred
                    location = details.get("location") or item.get("fallback_location") or "India"

                    # Qualifications & Experience
                    qual = details.get("qualification")
                    exp = details.get("experience")
                    
                    # Prepare rich description
                    desc_parts = []
                    if qual:
                        desc_parts.append(f"Qualification: {qual}")
                    if exp:
                        desc_parts.append(f"Experience: {exp}")
                    if location:
                        desc_parts.append(f"Job Location: {location}")
                    if item.get("fallback_content"):
                        desc_parts.append(item["fallback_content"])
                    full_desc = "\n\n".join(desc_parts)[:5000]

                    # CRITICAL: apply_url is strictly external, NEVER source domain!
                    apply_url = details.get("apply_url")

                    raw_jobs.append(
                        RawJob(
                            title=title,
                            company=company,
                            location=location,
                            description=full_desc if full_desc else title,
                            provenance=DiscoveryProvenanceDTO(
                                strategy_id=self.strategy_id,
                                adapter_id=self.strategy_id,
                                source_id=candidate.source_id,
                                source_type="direct_ats",
                                source_url=post_link,
                                apply_url=apply_url,  # External or None, NEVER source domain!
                                provider_name=self.ats_name,
                            ),
                        )
                    )
                except Exception as post_err:
                    logger.debug(f"Failed to scrape WordPress post {post_link}: {post_err}")

            result.raw_jobs = raw_jobs
            result.jobs_discovered = len(raw_jobs)
            result.success = len(raw_jobs) > 0 or not result.errors
            logger.info(f"WordPressAdapter discovered {len(raw_jobs)} deep jobs from {url}")

        except Exception as e:
            logger.debug(f"WordPress adapter execution error for {url}: {e}")
            result.success = False
            result.requests_attempted = 1
            result.errors.append(
                DiscoveryError(
                    error_type=DiscoveryErrorType.NETWORK_FAILURE,
                    strategy_id=self.strategy_id,
                    adapter_id=self.strategy_id,
                    candidate_id=candidate.candidate_id,
                    message=str(e),
                )
            )

        result.duration_seconds = time.monotonic() - start_time
        return result

    def _parse_rest_api_posts(self, response_bytes: bytes) -> List[Dict[str, Any]]:
        try:
            posts = json.loads(response_bytes.decode("utf-8", errors="replace"))
            if not isinstance(posts, list):
                return []
            items = []
            for p in posts:
                if not isinstance(p, dict):
                    continue
                link = p.get("link")
                if not link:
                    continue
                raw_title = p.get("title", {})
                title_html = raw_title.get("rendered", "") if isinstance(raw_title, dict) else str(raw_title)
                clean_title = unescape(re.sub(r"<[^>]+>", "", title_html)).strip()

                raw_content = p.get("content", {})
                content_html = raw_content.get("rendered", "") if isinstance(raw_content, dict) else str(raw_content)
                clean_desc = unescape(re.sub(r"<[^>]+>", " ", content_html))
                clean_desc = " ".join(clean_desc.split())

                items.append({
                    "link": link,
                    "fallback_title": clean_title,
                    "fallback_content": clean_desc[:2000],
                })
            return items
        except Exception:
            return []

    def _parse_sitemap_urls(self, response_bytes: bytes, sitemap_url: str) -> List[Dict[str, Any]]:
        try:
            root = ET.fromstring(response_bytes)
            items = []
            # Find namespace if present
            ns = ""
            if "}" in root.tag:
                ns = root.tag.split("}")[0] + "}"

            # Check if urlset
            for url_tag in root.findall(f"{ns}url"):
                loc = url_tag.find(f"{ns}loc")
                if loc is not None and loc.text:
                    link = loc.text.strip()
                    # Skip common non-job URLs
                    if any(skip in link.lower() for skip in ["/category/", "/tag/", "/author/", "/page/", "/about", "/contact", "/privacy"]):
                        continue
                    items.append({"link": link})

            return items
        except Exception as e:
            logger.debug(f"Failed to parse sitemap XML for {sitemap_url}: {e}")
            return []

    async def extract_jobs(
        self,
        response_data: bytes,
        candidate: StrategyCandidate,
    ) -> list[RawJob]:
        """
        Fast fallback extraction implementing ATSAdapter contract.
        """
        try:
            posts = self._parse_rest_api_posts(response_data)
            raw_jobs = []
            for p in posts:
                raw_jobs.append(
                    RawJob(
                        title=p.get("fallback_title", "Job Opening"),
                        company=candidate.source or "Direct Employer",
                        location="India",
                        description=p.get("fallback_content", ""),
                        provenance=DiscoveryProvenanceDTO(
                            strategy_id=self.strategy_id,
                            adapter_id=self.strategy_id,
                            source_id=candidate.source_id,
                            source_type="direct_ats",
                            source_url=p.get("link", candidate.target_url),
                            apply_url=None,  # NEVER source domain!
                            provider_name=self.ats_name,
                        ),
                    )
                )
            return raw_jobs
        except Exception:
            return []

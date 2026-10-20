"""
Post Scraper & High-Precision Official Link Extractor.
Ports and enhances the scoring algorithm from the scaper project (services/extractor.py)
to extract the real corporate apply link, true job location, and qualification from WordPress post pages.
"""
import re
import logging
from urllib.parse import urlparse
from typing import Optional, Dict, Any, List, Tuple
from bs4 import BeautifulSoup
from html import unescape

logger = logging.getLogger(__name__)

BLACKLIST_DOMAINS = [
    'telegram', 't.me', 'telegram.dog', 'whatsapp', 'wa.me', 'facebook', 'fb.com',
    'instagram', 'youtube', 'youtu.be', 'linkedin', 'twitter', 'x.com',
    'discord', 'pinterest', 'reddit', 'tiktok', 'snapchat',
    'openinapp', 'linktr.ee', 'bit.ly', 'goo.gl', 'tinyurl', 'cutt.ly',
    'addtoany', 'sharethis', 'share', 'mailto', 'wp.me'
]

IGNORE_TITLE_WORDS = {
    'off', 'campus', 'hiring', 'recruitment', 'job', 'jobs', 'vacancy', 'vacancies',
    'careers', 'career', '2024', '2025', '2026', '2027', 'freshers', 'fresher',
    'apply', 'online', 'drive', 'engineer', 'developer', 'analyst', 'manager',
    'specialist', 'associate', 'internship', 'intern', 'walkin', 'walk-in'
}


def extract_company_keywords(title: str) -> list[str]:
    """Extract candidate company tokens from job post title."""
    clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', title.lower()).split()
    return [w for w in clean if len(w) > 3 and w not in IGNORE_TITLE_WORDS]


def parse_wp_post_webpage(html_content: str, post_url: str) -> Dict[str, Any]:
    """
    Parses a WordPress post HTML page.
    Extracts:
      - title: Clean job title from H1 or meta
      - company: Hiring company name
      - location: Exact location from structured table or metadata
      - qualification: Required degrees / qualifications
      - experience: Required experience range
      - apply_url: Direct external corporate ATS / portal link (NEVER the source domain)
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    parsed_post = urlparse(post_url)
    source_domain = parsed_post.netloc.lower().replace('www.', '')

    # 1. Clean Title
    h1 = soup.find('h1')
    page_title = unescape(h1.get_text(strip=True)) if h1 else 'Unknown Title'
    page_title = re.sub(r'\s+', ' ', page_title).strip()

    # 2. Extract Company Name
    company = None
    comp_match = re.match(r'^(.*?)(?:\s+(?:Recruitment|Hiring|Jobs?|Walk-?in|Careers?|Off\s*Campus|Internship|Is\s+Hiring)\b)', page_title, re.IGNORECASE)
    if comp_match:
        company = comp_match.group(1).strip()
    if not company or len(company) < 2:
        # Fallback from domain / title
        tokens = page_title.split()
        company = tokens[0] if tokens else source_domain.split('.')[0].capitalize()

    # 3. Structured Details from Tables & Lists (Location, Qualification, Experience)
    location = None
    qualification = None
    experience = None

    for tr in soup.find_all('tr'):
        cells = tr.find_all(['td', 'th'])
        if len(cells) >= 2:
            lbl = cells[0].get_text(' ', strip=True).lower()
            val = unescape(cells[1].get_text(' ', strip=True))
            val_clean = re.sub(r'\s+', ' ', val).strip()

            if not location and any(k in lbl for k in ['location', 'job location', 'work location', 'posting location', 'place of posting']):
                # Verify it's not a link or boilerplate
                if len(val_clean) < 80 and not any(w in val_clean.lower() for w in ['apply', 'click', 'link', 'register']):
                    location = val_clean

            if not qualification and any(k in lbl for k in ['qualification', 'degree', 'education', 'eligibility']):
                if len(val_clean) < 150:
                    qualification = val_clean

            if not experience and any(k in lbl for k in ['experience', 'batch', 'years of experience']):
                if len(val_clean) < 80:
                    experience = val_clean

            if any(k in lbl for k in ['company', 'organization', 'company name']):
                if len(val_clean) < 60 and not any(w in val_clean.lower() for w in ['apply', 'click']):
                    company = val_clean

    # Fallback search for location in structured definition paragraphs
    if not location:
        for tag in soup.find_all(['p', 'li', 'div']):
            t = tag.get_text(' ', strip=True)
            m = re.search(r'(?:job\s+location|work\s+location|location)\s*[:\-]\s*([A-Za-z0-9\s,\/\-]+)', t, re.IGNORECASE)
            if m:
                cand = m.group(1).strip()
                if 2 < len(cand) < 60 and not any(w in cand.lower() for w in ['apply', 'click', 'link', 'http', 'here']):
                    location = cand
                    break

    # 4. High-Precision Official Link Extraction (scaper logic)
    company_keywords = extract_company_keywords(page_title)
    candidates: List[Dict[str, Any]] = []

    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if not href or not href.startswith('http'):
            continue

        try:
            cand_parsed = urlparse(href)
            cand_domain = cand_parsed.netloc.lower().replace('www.', '')
        except Exception:
            continue

        # RULE: NEVER ADD THE SOURCE DOMAIN AS JOB LINKS
        if source_domain in cand_domain or cand_domain in source_domain:
            continue

        # RULE: BLACKLIST FILTER
        if any(b in cand_domain for b in BLACKLIST_DOMAINS):
            continue

        link_text = a.get_text(' ', strip=True).lower()
        score = 10

        # Dedicated application forms (Microsoft Forms, Google Forms, Airtable)
        if any(f in cand_domain for f in ['forms.cloud.microsoft', 'forms.office.com', 'docs.google.com', 'forms.gle', 'airtable.com']):
            score += 150

        # Specific ATS platforms with job detail links
        if any(ats in cand_domain for ats in [
            'smartrecruiters.com', 'greenhouse.io', 'lever.co', 'myworkdayjobs.com',
            'workday.com', 'taleo.net', 'icims.com', 'ashbyhq.com', 'recruitee.com',
            'workable.com', 'bamboohr.com', 'keka.com', 'darwinbox.in', 'personio.com'
        ]):
            score += 150

        # Deep job posting paths (contains job id, req id, or jobdetails)
        cand_path = cand_parsed.path.lower()
        if any(p in cand_path for p in ['/jobdetails/', '/job/', '/jobs/', '/position/', '/posting/', '/opening/', '/requisition/']):
            score += 60
        if re.search(r'\d{4,}', cand_path) or re.search(r'[a-f0-9]{8,}', cand_path):
            score += 40

        # Context 1: Table row context
        parent_tr = a.find_parent('tr')
        if parent_tr:
            tr_text = parent_tr.get_text(' ', strip=True).lower()
            if any(k in tr_text for k in ['apply', 'link', 'click here', 'registration', 'official', 'form']):
                score += 80

        # Context 2: Keyword neighbors
        if any(k in link_text for k in ['apply', 'click here', 'register', 'apply now', 'official link', 'apply online', 'direct link', 'apply here']):
            score += 80

        # Context 3: Company Keyword in URL
        if company_keywords and any(c in href.lower() for c in company_keywords):
            score += 40

        # Context 4: Career / ATS keywords in URL
        if any(k in href.lower() for k in [
            'career', 'careers', 'job', 'jobs', 'recruitment', 'posting', 'position'
        ]):
            score += 20

        # CRITICAL PENALTY: Generic career/job portal homepages are NOT specific apply links!
        clean_path = cand_parsed.path.rstrip('/').lower()
        if clean_path in [
            '', '/careers', '/jobs', '/career', '/job-opportunities',
            '/about-us/careers', '/en/careers', '/en-in/careers',
            '/pages/careers', '/careers-home', '/jobs-home'
        ]:
            score -= 100

        candidates.append({
            'link': href,
            'text': link_text,
            'score': score
        })

    # Sort candidates by score descending
    candidates.sort(key=lambda x: x['score'], reverse=True)

    winner_link = None
    if candidates and candidates[0]['score'] >= 40:
        winner_link = candidates[0]['link']
    elif not candidates or (candidates and candidates[0]['score'] < 40):
        # Direct employer career page check:
        # If the page hosts an embedded job application form (e.g. Contact Form 7, WPForms, Gravity Forms, file upload),
        # the post page itself IS the direct apply link!
        has_form = bool(
            soup.find('form', class_=lambda c: c and any(f in str(c).lower() for f in ['wpcf7', 'gform', 'ninja', 'wpforms', 'job-application', 'apply']))
            or soup.find('input', type='file')
            or soup.find('form', action=lambda a: a and any(f in str(a).lower() for f in ['wpcf7', 'apply', 'job', 'career']))
        )
        is_direct_job_post = any(slug in post_url.lower() for slug in [
            '/opportunity/', '/opportunities/', '/odc_opportunities/', '/consulting_jobs/',
            '/job/', '/jobs/', '/position/', '/opening/', '/careers/'
        ])
        if has_form or is_direct_job_post:
            clean_post_path = urlparse(post_url).path.rstrip('/').lower()
            generic_listing_paths = [
                '', '/careers', '/jobs', '/career', '/job-opportunities',
                '/about-us/careers', '/en/careers', '/en-in/careers',
                '/careers/odc-opportunities', '/careers/opportunities',
                '/careers/consulting-jobs', '/odc_opportunities', '/opportunities', '/consulting_jobs'
            ]
            if clean_post_path not in generic_listing_paths:
                winner_link = post_url

    return {
        'title': page_title,
        'company': company,
        'location': location,
        'qualification': qualification,
        'experience': experience,
        'apply_url': winner_link  # Direct apply link or None, NEVER aggregator domain!
    }


import re
import unicodedata
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

def normalize_string(text: str) -> str:
    """Basic unicode and whitespace normalization."""
    if not text:
        return ""
    # Unicode NFKD normalizes characters (e.g., accents), then encode/decode ascii to strip combining chars
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    # Convert to lowercase
    text = text.lower()
    # Replace multiple whitespace characters with a single space
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def normalize_title(title: str) -> str:
    """Normalize a job title for comparison."""
    if not title:
        return ""
    title = normalize_string(title)
    # Remove common irrelevant prefixes/suffixes like "Remote", "(Remote)", "Hiring Now!"
    title = re.sub(r'\(?remote\)?', '', title, flags=re.IGNORECASE)
    title = re.sub(r'hiring now!?', '', title, flags=re.IGNORECASE)
    # Strip any dangling punctuation from the ends
    title = title.strip(' -,.|/()[]')
    # Ensure no double spaces after replacing words
    return re.sub(r'\s+', ' ', title).strip()

def normalize_company(company: str) -> str:
    """Normalize a company name for comparison, stripping legal entities."""
    if not company:
        return ""
    company = normalize_string(company)
    # Remove common legal suffixes and punctuation
    company = re.sub(r'\b(inc\.?|llc\.?|ltd\.?|corp\.?|corporation|plc\.?|co\.?)\b', '', company, flags=re.IGNORECASE)
    company = re.sub(r'[^\w\s]', '', company)
    return re.sub(r'\s+', ' ', company).strip()

def normalize_location(location: str) -> str:
    """Normalize location string."""
    if not location:
        return ""
    location = normalize_string(location)
    # Strip common punctuation that might differ (e.g., "San Francisco, CA" vs "San Francisco CA")
    location = location.replace(',', '')
    return re.sub(r'\s+', ' ', location).strip()

def normalize_url(url: str) -> str:
    """
    Normalize URLs by lowercasing scheme/host, removing trailing slashes,
    and stripping common tracking parameters.
    """
    if not url:
        return ""
    
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        
        # Remove trailing slash from path
        path = parsed.path
        if len(path) > 1 and path.endswith('/'):
            path = path[:-1]
            
        # Filter tracking parameters
        tracking_params = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'gh_jid', 'gh_src'}
        query_params = parse_qsl(parsed.query, keep_blank_values=True)
        filtered_query = [(k, v) for k, v in query_params if k.lower() not in tracking_params]
        query = urlencode(filtered_query)
        
        normalized = urlunparse((scheme, netloc, path, parsed.params, query, parsed.fragment))
        return normalized
    except Exception:
        # If parsing fails, just return the stripped URL
        return url.strip()

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

def clean_location_display(location: str) -> str:
    """
    Cleans and formats location strings for display while preserving
    proper Title Case, country/state abbreviations, and punctuation.
    Avoids destructive lowercasing.
    """
    if not location:
        return ""
    
    # Strip HTML tags if any leaked in
    text = re.sub(r'<[^>]+>', '', location)
    # Normalize unicode
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    
    # Handle pure remote variations
    if re.search(r'\b(?:remote|work\s+from\s+home|wfh|telecommute)\b', text, re.IGNORECASE):
        cleaned_no_remote = re.sub(r'\b(?:remote|job|position|work|role|anywhere|global|worldwide|100%)\b', '', text, flags=re.IGNORECASE).strip(' ,;-/()[]')
        if not cleaned_no_remote:
            return "Remote"
        return f"Remote ({cleaned_no_remote})"
        
    # Remove noisy bracketed job tags from location header
    text = re.sub(r'\(?\s*(?:hybrid|on-?site|remote|full-?time|part-?time)\s*\)?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[\s*(?:hybrid|on-?site|remote|full-?time|part-?time)\s*\]', '', text, flags=re.IGNORECASE)
    
    # Standardize comma and space separators
    text = re.sub(r'\s*,\s*', ', ', text)
    text = re.sub(r'\s*/\s*', ' / ', text)
    text = re.sub(r'\s+', ' ', text).strip(' ,;-/')
    
    if not text:
        return ""
        
    # If the text is all lowercase or all uppercase, convert to Title Case
    # while preserving known state/country abbreviations (CA, NY, UK, USA, NSW, QLD, etc.)
    COMMON_UPPER = {
        "CA", "NY", "TX", "WA", "FL", "IL", "PA", "OH", "GA", "NC", "MI", "NJ", "VA", "MA",
        "CO", "AZ", "TN", "MO", "MD", "WI", "MN", "OR", "SC", "AL", "LA", "KY", "OR", "OK",
        "CT", "UT", "IA", "NV", "AR", "MS", "KS", "NM", "NE", "WV", "ID", "HI", "NH", "ME",
        "RI", "MT", "DE", "SD", "ND", "AK", "DC", "VT", "WY",
        "UK", "USA", "US", "UAE", "EU", "APAC", "EMEA", "NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"
    }
    
    # Check if string lacks capitalization
    if text.islower() or text.isupper():
        parts = text.split(',')
        cleaned_parts = []
        for part in parts:
            words = part.strip().split()
            c_words = []
            for w in words:
                w_upper = w.upper()
                if w_upper in COMMON_UPPER:
                    c_words.append(w_upper)
                else:
                    c_words.append(w.capitalize())
            cleaned_parts.append(' '.join(c_words))
        text = ', '.join(cleaned_parts)
        
    return text.strip()

def normalize_location(location: str) -> str:
    """Normalize location string for deduplication comparison."""
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
            
        # Filter tracking parameters. DO NOT remove gh_jid, as it identifies the actual job!
        tracking_params = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'gh_src'}
        query_params = parse_qsl(parsed.query, keep_blank_values=True)
        filtered_query = [(k, v) for k, v in query_params if k.lower() not in tracking_params]
        query = urlencode(filtered_query)
        
        # We strip the fragment to avoid SPA hash routing causing duplicate canonical jobs
        # However, if the fragment is the ONLY differentiator, it might cause issues.
        # But generally, apply URLs without fragment represent the same job.
        normalized = urlunparse((scheme, netloc, path, parsed.params, query, ""))
        return normalized
    except Exception:
        # If parsing fails, just return the stripped URL
        return url.strip()

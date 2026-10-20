import re
from typing import Optional, Tuple, Dict, Any

# Degree regex patterns - tailored for Indian IT and global tech hiring
DEGREE_PATTERNS = [
    ("MCA", r"\b(?:mca|m\.c\.a|master\s+of\s+computer\s+applications?|computer\s+applications?)\b"),
    ("M.Tech", r"\b(?:m\.?tech|master\s+of\s+technology|m\.?e|master\s+of\s+engineering)\b"),
    ("B.Tech", r"\b(?:b\.?tech|b\.?e|bachelor\s+of\s+engineering|bachelor\s+of\s+technology)\b"),
    ("BCA", r"\b(?:bca|b\.c\.a|bachelor\s+of\s+computer\s+applications?)\b"),
    ("B.Sc CS", r"\b(?:b\.?sc\s+(?:cs|it|computer\s+science)|bachelor\s+of\s+science\s+in\s+computer)\b"),
    ("Master's", r"\b(?:master'?s\s+degree|ms\s+in\s+computer|post\s*graduate)\b"),
    ("Bachelor's", r"\b(?:bachelor'?s\s+degree|under\s*graduate)\b"),
    ("Any Graduate", r"\b(?:any\s+graduate|any\s+degree|graduation\s+not\s+required|all\s+graduates?)\b"),
]

# Role taxonomy definitions
ROLE_TAXONOMY = {
    "frontend": [
        r"\bfrontend\b", r"\bfront-end\b", r"\breact\b", r"\bvue\b", r"\bangular\b",
        r"\bui\s+developer\b", r"\bui/ux\b", r"\bnext\.?js\b", r"\bjavascript\s+developer\b"
    ],
    "backend": [
        r"\bbackend\b", r"\bback-end\b", r"\bpython\s+developer\b", r"\bjava\s+developer\b",
        r"\bgolang\b", r"\bnode\.?js\b", r"\bdjango\b", r"\bfastapi\b", r"\bspring\s+boot\b",
        r"\bserver\s+engineer\b", r"\bc\+\+\s+developer\b", r"\b\.net\s+developer\b"
    ],
    "fullstack": [
        r"\bfull\s*stack\b", r"\bfullstack\b", r"\bmearn\b", r"\bmean\s+stack\b"
    ],
    "mobile": [
        r"\bandroid\b", r"\bios\b", r"\bflutter\b", r"\breact\s+native\b", r"\bmobile\s+developer\b", r"\bswift\b", r"\bkotlin\b"
    ],
    "data_ai": [
        r"\bdata\s+scientist\b", r"\bdata\s+analyst\b", r"\bdata\s+engineer\b",
        r"\bmachine\s+learning\b", r"\bml\s+engineer\b", r"\bai\s+engineer\b",
        r"\bdeep\s+learning\b", r"\bnlp\b", r"\bcomputer\s+vision\b", r"\bpower\s+bi\b"
    ],
    "devops_cloud": [
        r"\bdevops\b", r"\bcloud\s+engineer\b", r"\bsite\s+reliability\b", r"\bsre\b",
        r"\bkubernetes\b", r"\baws\b", r"\bazure\b", r"\bgcp\b", r"\binfrastructure\s+engineer\b",
        r"\bsystem\s+administrator\b"
    ],
    "qa_testing": [
        r"\bqa\b", r"\btest\s+engineer\b", r"\bsdet\b", r"\bquality\s+assurance\b",
        r"\bautomation\s+tester\b", r"\bselenium\b", r"\bperformance\s+tester\b"
    ],
    "product_management": [
        r"\bproduct\s+manager\b", r"\btechnical\s+product\s+manager\b", r"\bproduct\s+owner\b",
        r"\bbusiness\s+analyst\b", r"\bscrum\s+master\b"
    ],
    "software_engineer": [
        r"\bsoftware\s+engineer\b", r"\bsoftware\s+developer\b", r"\bsde\b",
        r"\bprogrammer\b", r"\bapplication\s+developer\b", r"\bmember\s+technical\s+staff\b",
        r"\btech\s+lead\b"
    ]
}

def extract_degree(text: Optional[str]) -> Optional[str]:
    """
    Extracts the highest/most specific degree required from text.
    Prioritizes MCA, M.Tech, B.Tech, etc.
    """
    if not text:
        return None
    for label, pattern in DEGREE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return label
    return None

def extract_salary(text: Optional[str]) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Extracts salary range and currency from job descriptions or salary strings.
    Handles Indian LPA (Lakhs Per Annum) and USD formats.
    Returns: (salary_min, salary_max, currency)
    """
    if not text:
        return None, None, None

    # Pattern 1: LPA format: "4 - 8 LPA", "6.5 to 10 Lakhs", "₹5,00,000 - 10,00,000"
    lpa_range = re.search(r'(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?|lacs?|lac)', text, re.IGNORECASE)
    if lpa_range:
        min_val = float(lpa_range.group(1)) * 100000
        max_val = float(lpa_range.group(2)) * 100000
        return min_val, max_val, "INR"

    single_lpa = re.search(r'(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?|lacs?|lac)', text, re.IGNORECASE)
    if single_lpa:
        val = float(single_lpa.group(1)) * 100000
        return val, val, "INR"

    # Pattern 2: Raw INR numbers (e.g. ₹ 400000 - ₹ 800000)
    inr_raw = re.search(r'(?:₹|inr)\s*(\d{5,8})\s*(?:-|to)\s*(?:₹|inr)?\s*(\d{5,8})', text, re.IGNORECASE)
    if inr_raw:
        return float(inr_raw.group(1)), float(inr_raw.group(2)), "INR"

    # Pattern 3: USD $XX,XXX - $YY,YYY or $80k - $120k
    usd_k = re.search(r'\$\s*(\d{2,3})\s*k\s*(?:-|to)\s*\$?\s*(\d{2,3})\s*k', text, re.IGNORECASE)
    if usd_k:
        return float(usd_k.group(1)) * 1000, float(usd_k.group(2)) * 1000, "USD"

    usd_full = re.search(r'\$\s*(\d{2,3},\d{3})\s*(?:-|to)\s*\$?\s*(\d{2,3},\d{3})', text)
    if usd_full:
        min_val = float(usd_full.group(1).replace(',', ''))
        max_val = float(usd_full.group(2).replace(',', ''))
        return min_val, max_val, "USD"

    return None, None, None

def classify_role(title: str, description: Optional[str] = "") -> str:
    """
    Classifies job title and description into a canonical role taxonomy.
    """
    combined = f"{title} {description or ''}".lower()
    
    # First check title explicitly for highest precision
    for role, patterns in ROLE_TAXONOMY.items():
        for p in patterns:
            if re.search(p, title.lower()):
                return role

    # Fallback: check combined text
    for role, patterns in ROLE_TAXONOMY.items():
        if role == "software_engineer":
            continue
        for p in patterns:
            if re.search(p, combined):
                return role

    return "software_engineer"

def extract_experience(title: str, text: Optional[str] = "") -> str:
    """
    Extracts experience level: 'fresher', 'junior', 'mid', 'senior'
    Fresher is 0-1 years (intern, trainee, campus, graduate, apprentice, entry level, 0 Yrs, no experience).
    """
    t_lower = (title or "").lower()
    text_lower = (text or "").lower()
    combined = f"{t_lower} {text_lower}"

    # Priority 1: Clear Fresher / Intern markers in TITLE
    if re.search(r'\b(?:fresher|intern|internship|trainee|campus|graduate|graduates|apprentice|entry[\s-]level|student)\b', t_lower):
        return "fresher"

    # Priority 2: Senior / Lead in TITLE
    if re.search(r'\b(?:senior|sr\.?|lead|principal|architect|staff|director|head|vp|manager|chief)\b', t_lower):
        return "senior"

    # Priority 3: Mid / Junior in TITLE
    if re.search(r'\b(?:mid|intermediate)\b', t_lower):
        return "mid"
    if re.search(r'\b(?:junior|jr\.?|associate)\b', t_lower):
        return "junior"

    # Priority 4: Explicit year patterns in text or title
    if re.search(r'\b(?:5\+|6\+|7\+|8\+|9\+|10\+|[5-9]\d*)\s*years?\b', combined):
        return "senior"
    if re.search(r'\b(?:3\s*-\s*5|4\s*-\s*6|3\+|4\+)\s*years?\b', combined):
        return "mid"
    if re.search(r'\b(?:1\s*-\s*3|2\s*-\s*4|1\s*-\s*2|0\s*-\s*2|1\+|2\+)\s*years?\b', combined):
        return "junior"
    if re.search(r'\b(?:0\s*-\s*1|0\s*-\s*0|0\s*years?|no\s+experience|freshers?\s+can\s+apply|202[4-7]\s+batch)\b', combined):
        return "fresher"

    # Fallback checks in combined text
    if re.search(r'\b(?:fresher|entry[\s-]level|trainee|intern|internship)\b', text_lower):
        return "fresher"
    if re.search(r'\b(?:senior|principal|architect|director)\b', text_lower):
        return "senior"

    return "junior"

# South India & Chennai micro-corridor mapping
CHENNAI_MICRO_CORRIDORS = [
    (r"\b(?:tidel\s+park|taramani|ascendas)\b", "Chennai, Tamil Nadu", "OMR / Taramani TIDEL Park"),
    (r"\b(?:siruseri|sipcot\s+it\s+park|naval[lu]r|egattur)\b", "Chennai, Tamil Nadu", "OMR / Siruseri SIPCOT"),
    (r"\b(?:sholinganall[lu]r|elcot\s+sez)\b", "Chennai, Tamil Nadu", "OMR / Sholinganallur ELCOT"),
    (r"\b(?:perungudi|kandanchavadi|thoraipakkam|karapakkam)\b", "Chennai, Tamil Nadu", "OMR / Perungudi"),
    (r"\b(?:guindy|olympia\s+tech\s+park|ekkatuthangal)\b", "Chennai, Tamil Nadu", "Guindy / Olympia Tech Park"),
    (r"\b(?:dlf\s+(?:porur|cybercity)|porur|manapakkam|commerzone)\b", "Chennai, Tamil Nadu", "DLF Cybercity Porur"),
    (r"\b(?:mepz|tambaram|chromepet)\b", "Chennai, Tamil Nadu", "GST Road / MEPZ Tambaram"),
    (r"\b(?:mahindra\s+world\s+city|chengalpattu|paranur|maraimalai\s+nagar)\b", "Chennai, Tamil Nadu", "GST Road / Mahindra World City"),
    (r"\b(?:ambattur|prince\s+info\s+park|ambit\s+it\s+park|padi)\b", "Chennai, Tamil Nadu", "Ambattur IT Park"),
    (r"\b(?:sri\s+city|tada|gummidipoondi)\b", "Sri City, Border/Chennai", "Sri City SEZ"),
    (r"\b(?:coimbatore|kovai|saravanampatti|chil\s+sez|eachanari)\b", "Coimbatore, Tamil Nadu", "Coimbatore TIDEL / CHIL SEZ"),
    (r"\b(?:madurai|vadapalanji)\b", "Madurai, Tamil Nadu", "Madurai ELCOT"),
    (r"\b(?:trichy|tiruchirappalli|navalpattu)\b", "Tiruchirappalli, Tamil Nadu", "Trichy ELCOT"),
    (r"\b(?:hosur)\b", "Hosur, Tamil Nadu", "Hosur Tech / Manufacturing"),
    (r"\b(?:bengaluru|bangalore|whitefield|electronic\s+city|manyata|bellandur)\b", "Bengaluru, Karnataka", "Bengaluru Tech Hub"),
    (r"\b(?:hyderabad|hitec\s+city|gachibowli|madhapur)\b", "Hyderabad, Telangana", "Hyderabad Tech Hub"),
    (r"\b(?:kochi|cochin|infopark|kakkanad|trivandrum|technopark)\b", "Kerala Tech Hub", "Kerala IT Park"),
]

def normalize_south_india_location(location: Optional[str], text: Optional[str] = "") -> Tuple[str, Optional[str]]:
    """
    Normalizes local Chennai tech parks and South India regional corridors.
    Returns: (normalized_location, corridor_name)
    """
    # 1. If explicit location is given, match on location directly without text noise
    loc_clean = (location or "").strip()
    if loc_clean and loc_clean.lower() not in ("unspecified", "india", ""):
        for pattern, canonical_loc, corridor in CHENNAI_MICRO_CORRIDORS:
            if re.search(pattern, loc_clean, re.IGNORECASE):
                return canonical_loc, corridor
        if "chennai" in loc_clean.lower() or "madras" in loc_clean.lower():
            return "Chennai, Tamil Nadu", "Chennai Central"
        return loc_clean, None

    # 2. Only if location is empty or generic, inspect text (e.g. title / structured header)
    text_clean = (text or "").strip()
    if text_clean:
        for pattern, canonical_loc, corridor in CHENNAI_MICRO_CORRIDORS:
            if re.search(pattern, text_clean, re.IGNORECASE):
                return canonical_loc, corridor
        if "chennai" in text_clean.lower() or "madras" in text_clean.lower():
            return "Chennai, Tamil Nadu", "Chennai Central"

    return loc_clean or "India", None

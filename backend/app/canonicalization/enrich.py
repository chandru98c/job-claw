import re
from typing import Optional, Tuple, Dict, Any

# Degree regex patterns - strictly anchored to avoid false positives (e.g. 'be' as a verb)
DEGREE_PATTERNS = [
    ("MCA", r"\b(?:mca|m\.c\.a|master\s+of\s+computer\s+applications?)\b"),
    ("M.Tech", r"(?:\b(?:m\.?tech|master\s+of\s+technology|master\s+of\s+engineering)\b|\bm\.e\.?(?!\w)|me\s*[/&]\s*m\.?tech)"),
    ("B.Tech", r"(?:\b(?:b\.?tech|bachelor\s+of\s+engineering|bachelor\s+of\s+technology)\b|\bb\.e\.?(?!\w)|be\s*[/&]\s*b\.?tech|b\.?tech\s*[/&]\s*be)"),
    ("BCA", r"\b(?:bca|b\.c\.a|bachelor\s+of\s+computer\s+applications?)\b"),
    ("B.Sc CS", r"\b(?:b\.?sc\s+(?:in\s+)?(?:cs|it|computer\s+science)|bachelor\s+of\s+science\s+(?:in\s+)?(?:computer\s+science|cs|it))\b"),
    ("Master's", r"\b(?:master'?s\s+degree|ms\s+in\s+(?:computer|cs|engineering|science)|m\.s\.\s+degree|post\s*graduate\s+degree)\b"),
    ("Bachelor's", r"\b(?:bachelor'?s\s+degree|under\s*graduate\s+degree|b\.s\.\s+degree|bs\s+degree)\b"),
    ("Any Graduate", r"\b(?:any\s+graduate|any\s+degree|graduation\s+not\s+required)\b"),
]

def extract_qualification_section(text: Optional[str]) -> str:
    """
    Extracts the qualifications/requirements section from a job description,
    stripping HTML and bounding the search to prevent boilerplate false positives.
    """
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', text)
    match = re.search(
        r'(?:qualifications?|requirements?|education|eligibility|prerequisites?|what\s+you(?:(?:\'ll)?|\s+will)\s+need|basic\s+qualifications|who\s+you\s+are|minimum\s+qualifications)'
        r'[:\s\n\-–]+(.*?)(?:what\s+we\s+offer|benefits|about\s+(?:us|the\s+company)|perks|equal\s+opportunity|how\s+to\s+apply|$)',
        clean,
        re.IGNORECASE | re.DOTALL
    )
    if match:
        return match.group(1)[:4000]
    return clean[:4000]

def extract_degree(text: Optional[str]) -> Optional[str]:
    """
    Extracts the minimum required degree from text.
    Handles compound phrasing like 'Bachelor's or Master's degree' correctly by recognizing
    that a Bachelor's degree satisfies the minimum requirement.
    Returns None if no degree is explicitly required.
    """
    if not text:
        return None
        
    qual_section = extract_qualification_section(text) or text
    clean = re.sub(r'<[^>]+>', ' ', qual_section).lower()

    # 1. Specialized degrees (MCA, BCA, B.Sc CS)
    if re.search(r"\b(?:mca|m\.c\.a|master\s+of\s+computer\s+applications?)\b", clean):
        return "MCA"
    if re.search(r"\b(?:bca|b\.c\.a|bachelor\s+of\s+computer\s+applications?)\b", clean):
        return "BCA"
    if re.search(r"\b(?:b\.?sc\s+(?:in\s+)?(?:cs|it|computer\s+science)|bachelor\s+of\s+science\s+(?:in\s+)?(?:computer\s+science|cs|it))\b", clean):
        return "B.Sc CS"

    # 2. Check for engineering degrees
    has_btech = bool(re.search(r"(?:\b(?:b\.?tech|bachelor\s+of\s+engineering|bachelor\s+of\s+technology)\b|\bb\.e\b(?!\w)|be\s*[/&]\s*b\.?tech|b\.?tech\s*[/&]\s*be)", clean))
    has_mtech = bool(re.search(r"(?:\b(?:m\.?tech|master\s+of\s+technology|master\s+of\s+engineering)\b|\bm\.e\b(?!\w)|me\s*[/&]\s*m\.?tech)", clean))

    # 3. Check for general Bachelor's and Master's
    has_bachelor = bool(re.search(r"\b(?:bachelor'?s(?:\s+degree)?|b\.?s\.?\s+degree|b\.?a\.?\s+degree|under\s*graduate(?:\s+degree)?)\b", clean))
    has_master = bool(re.search(r"\b(?:master'?s(?:\s+degree)?|m\.?s\.?\s+degree|post\s*graduate(?:\s+degree)?)\b", clean))

    # Minimum entry requirement principle:
    # If a Bachelor's degree (or B.Tech) is accepted (e.g. "Bachelor's or Master's degree"),
    # the minimum required education is Bachelor's / B.Tech!
    if has_btech:
        return "B.Tech"
    if has_bachelor:
        return "Bachelor's"
    if has_mtech:
        return "M.Tech"
    if has_master:
        return "Master's"

    if re.search(r"\b(?:any\s+graduate|any\s+degree|graduation\s+not\s+required)\b", clean):
        return "Any Graduate"

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

def extract_experience(title: str, text: Optional[str] = "") -> Optional[str]:
    """
    Extracts candidate experience level accurately: 'fresher', 'junior', 'mid', 'senior'
    Returns None if experience is not explicitly specified (no false defaults).
    
    CRITICAL RULE:
    Explicit numerical requirements in the job description (e.g. '2-3 years of experience')
    ARE GROUND TRUTH and MUST take precedence over ambiguous title words (e.g. 'Senior Associate').
    """
    t_lower = (title or "").lower()
    desc_clean = re.sub(r'<[^>]+>', ' ', text or "")

    # 1. First, check candidate requirements in text for explicit years of experience
    # Filter out company history boilerplate lines (e.g. "for 10 years", "founded 15 years ago")
    filtered_lines = []
    for line in desc_clean.split("\n"):
        line_l = line.lower()
        if any(h in line_l for h in (
            "founded in", "in business for", "serving customers for", "years in business", 
            "years of combined", "company has", "experience delivering", "years of innovation",
            "over the past", "for more than", "history of"
        )):
            continue
        filtered_lines.append(line)
    body = " ".join(filtered_lines)

    # Check for explicit fresher phrasing in text
    if re.search(r"\b(?:no\s+prior\s+(?:sales\s+|work\s+)?experience|no\s+experience\s+required|freshers?\s+can\s+apply|fresh\s+graduates?\s+can\s+apply|202[4-7]\s+batch)\b", body, re.IGNORECASE):
        return "fresher"

    # Precise anchored patterns for candidate experience:
    # Pattern 1: Range "2-3 years of experience", "2 to 4 years experience", "experience: 2-3 yrs"
    range_match = re.search(
        r'''(?x)
        (?:
            # e.g., "2-4 years of experience", "2 to 3 yrs of relevant experience"
            \b(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\s*(?:years?|yrs?)(?:\s+(?:of\s+)?(?:relevant|professional|hands[- ]on|industry|work|direct)?\s*experience)?
            |
            # e.g., "experience : 2 - 3 years", "experience required: 2-4 yrs"
            \bexperience(?:\s+required)?\s*[:\-]\s*(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\s*(?:years?|yrs?)
        )
        ''', 
        body, 
        re.IGNORECASE
    )
    if range_match:
        groups = [g for g in range_match.groups() if g is not None]
        if len(groups) >= 2:
            min_yr = int(groups[0])
            max_yr = int(groups[1])
            if min_yr >= 5:
                return "senior"
            elif min_yr >= 3:
                return "mid"
            elif max_yr <= 1:
                return "fresher"
            else: # min_yr is 1 or 2 (e.g. 1-2, 1-3, 2-3, 2-4)
                if max_yr >= 5:
                    return "mid" # e.g. 2-5 or 2-6 years
                return "junior"  # 1-3, 2-3, 2-4 years is Junior!

    # Pattern 2: Single number anchored to experience:
    # "minimum 5 years of experience", "3+ years of experience", "at least 2 years experience"
    single_match = re.search(
        r'''(?x)
        (?:
            # "min 3 years of experience", "at least 5 years of experience"
            \b(?:min(?:imum)?|at\s+least)\s*(?:of\s+)?(\d{1,2})\s*(?:\+|plus)?\s*(?:years?|yrs?)(?:\s+(?:of\s+)?(?:relevant|professional|hands[- ]on|work)?\s*experience)?
            |
            # "5+ years of experience", "3+ yrs experience"
            \b(\d{1,2})\s*(?:\+|plus)\s*(?:years?|yrs?)\s*(?:of\s+)?(?:relevant|professional|hands[- ]on|work)?\s*experience
            |
            # "experience : 3+ years", "experience: 5 years"
            \bexperience(?:\s+required)?\s*[:\-]\s*(\d{1,2})\s*(?:\+|plus)?\s*(?:years?|yrs?)
            |
            # "3 years of relevant experience"
            \b(\d{1,2})\s*(?:years?|yrs?)\s+(?:of\s+)(?:relevant|professional|hands[- ]on|work)?\s*experience
        )
        ''',
        body,
        re.IGNORECASE
    )
    if single_match:
        groups = [g for g in single_match.groups() if g is not None]
        if groups:
            yr = int(groups[0])
            if yr >= 5:
                return "senior"
            elif yr >= 3:
                return "mid"
            elif yr >= 1:
                return "junior"
            elif yr == 0:
                return "fresher"

    # 2. If NO numerical requirement is found in the description, inspect Title Keywords as Fallback
    # Priority 1: Fresher / Intern in title
    if re.search(r"\b(?:fresher|freshers|intern|internship|trainee|campus|apprentice|entry[\s-]level|student)\b", t_lower):
        return "fresher"

    # Priority 2: Junior / Associate in title
    if re.search(r"\b(?:junior|jr\.?)\b", t_lower):
        return "junior"
    if "senior associate" in t_lower:
        # Senior Associate is standard level-2 (2-3 years), NOT senior!
        return "junior"
    if re.search(r"\b(?:associate|assistant)\b", t_lower) and not re.search(r"\b(?:director|vp|vice\s+president|head)\b", t_lower):
        return "junior"

    # Priority 3: Senior / Lead / Principal in title (when no explicit years stated)
    if re.search(r"\b(?:senior|sr\.?|lead|principal|architect|staff|director|head|vp|vice\s+president|chief)\b", t_lower):
        return "senior"

    # Priority 4: Mid in title
    if re.search(r"\b(?:mid[\s-]level|intermediate)\b", t_lower):
        return "mid"

    # Explicit level mentions in body text
    if re.search(r"\b(?:entry[\s-]level|graduate\s+role)\b", body, re.IGNORECASE):
        return "fresher"

    return None

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
    Never forces 'India' if unstated.
    """
    loc_clean = (location or "").strip()
    
    # Check for remote
    if loc_clean and "remote" in loc_clean.lower():
        return "Remote", "Remote"
        
    # 1. If explicit location is given, match on location directly without text noise
    if loc_clean and loc_clean.lower() not in ("unspecified", "india", ""):
        for pattern, canonical_loc, corridor in CHENNAI_MICRO_CORRIDORS:
            if re.search(pattern, loc_clean, re.IGNORECASE):
                return canonical_loc, corridor
        if "chennai" in loc_clean.lower() or "madras" in loc_clean.lower():
            return "Chennai, Tamil Nadu", "Chennai Central"
        return loc_clean, None

    # 2. Only if location is empty or generic, check if title has explicit city
    text_clean = (text or "").strip()
    if text_clean:
        for pattern, canonical_loc, corridor in CHENNAI_MICRO_CORRIDORS:
            if re.search(pattern, text_clean, re.IGNORECASE):
                return canonical_loc, corridor
        if "chennai" in text_clean.lower() or "madras" in text_clean.lower():
            return "Chennai, Tamil Nadu", "Chennai Central"

    return loc_clean or "Unspecified", None

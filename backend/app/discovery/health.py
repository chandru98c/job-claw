import enum
from datetime import datetime, timedelta, timezone
from typing import Optional

# Configuration Constants
BASE_BACKOFF_SECONDS = 60
MAX_BACKOFF_SECONDS = 86400
CIRCUIT_FAILURE_THRESHOLD = 3

class ErrorClassification(str, enum.Enum):
    RETRYABLE_TRANSIENT = "RETRYABLE_TRANSIENT"  # 429, 500, 502, 503, 504, Timeout
    ACCESS_DENIED = "ACCESS_DENIED"              # 403
    NOT_FOUND = "NOT_FOUND"                      # 404
    UNAUTHORIZED = "UNAUTHORIZED"                # 401
    PARSING_ERROR = "PARSING_ERROR"              # Adapter data extraction failure
    UNKNOWN = "UNKNOWN"

def calculate_backoff(failure_count: int, retry_after: Optional[int] = None) -> int:
    """
    Calculate the cooldown duration in seconds using bounded exponential backoff.
    If retry_after is provided, it takes precedence, but is capped at MAX_BACKOFF_SECONDS.
    """
    if retry_after is not None and retry_after > 0:
        return min(retry_after, MAX_BACKOFF_SECONDS)
        
    if failure_count <= 0:
        return 0
        
    # Exponential backoff: BASE * 2^(failure_count - 1)
    # failure 1 -> 60s
    # failure 2 -> 120s
    # failure 3 -> 240s
    delay = BASE_BACKOFF_SECONDS * (2 ** (failure_count - 1))
    return min(delay, MAX_BACKOFF_SECONDS)

def classify_error(status_code: Optional[int] = None, error_msg: Optional[str] = None) -> ErrorClassification:
    """
    Classify the failure to determine semantic meaning.
    """
    if error_msg and status_code is None:
        # Try to extract HTTP status code from strings like "HTTP 403" or "404 Not Found"
        import re
        match = re.search(r'\b(401|403|404|408|429|500|502|503|504)\b', error_msg)
        if match:
            status_code = int(match.group(1))

    if status_code is not None:
        if status_code in (429, 408, 500, 502, 503, 504):
            return ErrorClassification.RETRYABLE_TRANSIENT
        if status_code == 403:
            return ErrorClassification.ACCESS_DENIED
        if status_code == 404:
            return ErrorClassification.NOT_FOUND
        if status_code == 401:
            return ErrorClassification.UNAUTHORIZED
    
    if error_msg:
        error_msg_lower = error_msg.lower()
        if "timeout" in error_msg_lower or "connection" in error_msg_lower or "network" in error_msg_lower:
            return ErrorClassification.RETRYABLE_TRANSIENT
        if "parse" in error_msg_lower or "extract" in error_msg_lower or "validation" in error_msg_lower or "format" in error_msg_lower or "json" in error_msg_lower:
            return ErrorClassification.PARSING_ERROR
            
    return ErrorClassification.UNKNOWN

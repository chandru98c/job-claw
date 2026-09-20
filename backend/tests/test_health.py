import pytest
from app.discovery.health import calculate_backoff, classify_error, ErrorClassification, BASE_BACKOFF_SECONDS, MAX_BACKOFF_SECONDS

def test_calculate_backoff():
    # Test base backoff scaling
    assert calculate_backoff(1) == BASE_BACKOFF_SECONDS
    assert calculate_backoff(2) == BASE_BACKOFF_SECONDS * 2
    assert calculate_backoff(3) == BASE_BACKOFF_SECONDS * 4
    
    # Test bounds
    assert calculate_backoff(0) == 0
    assert calculate_backoff(-1) == 0
    assert calculate_backoff(20) == MAX_BACKOFF_SECONDS  # Should cap out
    
def test_calculate_backoff_with_retry_after():
    # If retry_after is provided, it overrides calculation
    assert calculate_backoff(1, retry_after=120) == 120
    assert calculate_backoff(3, retry_after=5) == 5
    
    # But retry_after is still capped at max
    assert calculate_backoff(1, retry_after=MAX_BACKOFF_SECONDS + 1000) == MAX_BACKOFF_SECONDS

def test_classify_error_status_codes():
    assert classify_error(status_code=429) == ErrorClassification.RETRYABLE_TRANSIENT
    assert classify_error(status_code=500) == ErrorClassification.RETRYABLE_TRANSIENT
    assert classify_error(status_code=502) == ErrorClassification.RETRYABLE_TRANSIENT
    assert classify_error(status_code=403) == ErrorClassification.ACCESS_DENIED
    assert classify_error(status_code=404) == ErrorClassification.NOT_FOUND
    assert classify_error(status_code=401) == ErrorClassification.UNAUTHORIZED
    assert classify_error(status_code=400) == ErrorClassification.UNKNOWN
    
def test_classify_error_messages():
    assert classify_error(error_msg="Connection timeout occurred") == ErrorClassification.RETRYABLE_TRANSIENT
    assert classify_error(error_msg="Failed to parse JSON") == ErrorClassification.PARSING_ERROR
    assert classify_error(error_msg="Could not extract job title") == ErrorClassification.PARSING_ERROR
    assert classify_error(error_msg="HTTP 403 Forbidden") == ErrorClassification.ACCESS_DENIED
    assert classify_error(error_msg="Client error '404 Not Found' for url") == ErrorClassification.NOT_FOUND
    assert classify_error(error_msg="Some random error") == ErrorClassification.UNKNOWN


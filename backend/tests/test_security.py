import pytest
from app.core.security import UrlValidator, SSRFViolationError
from unittest import mock
import socket

def test_unsupported_schemes():
    with pytest.raises(SSRFViolationError, match="Unsupported scheme"):
        UrlValidator.validate_and_resolve("ftp://example.com/file")
    with pytest.raises(SSRFViolationError, match="Unsupported scheme"):
        UrlValidator.validate_and_resolve("file:///etc/passwd")

def test_embedded_credentials():
    with pytest.raises(SSRFViolationError, match="Credentials embedded"):
        UrlValidator.validate_and_resolve("https://user:pass@example.com")

def test_malformed_url():
    with pytest.raises(SSRFViolationError):
        # We also catch missing hostnames
        UrlValidator.validate_and_resolve("http://")

def test_dangerous_ports():
    with pytest.raises(SSRFViolationError, match="Dangerous port"):
        UrlValidator.validate_and_resolve("http://example.com:22")
    with pytest.raises(SSRFViolationError, match="Dangerous port"):
        UrlValidator.validate_and_resolve("http://example.com:6379")
    # Allowed ports should pass if DNS resolves securely
    with mock.patch("app.core.security._original_getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 8080))]):
        assert UrlValidator.validate_and_resolve("http://example.com:8080")[0] == "http://example.com:8080"

@pytest.mark.parametrize("url, resolved_ip, should_raise", [
    ("http://localhost", "127.0.0.1", True),
    ("http://127.0.0.1", "127.0.0.1", True),
    ("http://0.0.0.0", "0.0.0.0", True),
    ("http://10.0.0.1", "10.0.0.1", True), # Private IPv4
    ("http://172.16.0.1", "172.16.0.1", True), # Private IPv4
    ("http://192.168.1.1", "192.168.1.1", True), # Private IPv4
    ("http://[fd00::1]", "fd00::1", True), # Private IPv6
    ("http://169.254.169.254", "169.254.169.254", True), # Link-local / Cloud metadata
    ("http://metadata.google.internal", "169.254.169.254", True), # Cloud metadata hostname
    ("https://example.com", "93.184.216.34", False), # Public IP
])
def test_ip_resolution_security(url, resolved_ip, should_raise):
    with mock.patch("app.core.security._original_getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (resolved_ip, 80))]):
        if should_raise:
            with pytest.raises(SSRFViolationError):
                UrlValidator.validate_and_resolve(url)
        else:
            UrlValidator.validate_and_resolve(url)

def test_dns_rebinding_mixed_resolution():
    """
    If a DNS record resolves to multiple IPs and even ONE is private,
    we must reject it to protect against DNS rebinding / SSRF.
    """
    mixed_ips = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)), # Public
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.100", 80)), # Private
    ]
    with mock.patch("app.core.security._original_getaddrinfo", return_value=mixed_ips):
        with pytest.raises(SSRFViolationError, match="resolved to unsafe IP"):
            UrlValidator.validate_and_resolve("http://rebind.example.com")

def test_dns_rebinding_toctou_mitigation():
    """
    Test that the patched getaddrinfo returns the pinned IP.
    """
    from app.core.security import _dns_override
    
    # Simulate SafeHTTPClient pinning the IP
    token = _dns_override.set({
        'host': 'example.com',
        'result': (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))
    })
    try:
        # Call the monkey-patched getaddrinfo
        result = socket.getaddrinfo("example.com", 443)
        assert result[0][4][0] == "93.184.216.34"
    finally:
        _dns_override.reset(token)

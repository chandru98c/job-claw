import urllib.parse
import socket
import ipaddress
import os
import logging
from contextvars import ContextVar

logger = logging.getLogger(__name__)

# Used to protect against DNS rebinding (TOCTOU)
_dns_override = ContextVar('dns_override', default=None)
_original_getaddrinfo = socket.getaddrinfo

def _safe_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    override = _dns_override.get()
    if override and host == override['host']:
        # Return the pre-resolved IP instead of doing a real DNS lookup
        return [override['result']]
    return _original_getaddrinfo(host, port, family, type, proto, flags)

# Monkey-patch socket.getaddrinfo
socket.getaddrinfo = _safe_getaddrinfo

class SecurityException(Exception):
    pass

class SSRFViolationError(SecurityException):
    pass

def is_safe_ip(ip_str: str) -> bool:
    """Returns True if the IP address is considered safe (public, non-reserved)."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    # Block all private, loopback, link-local, multicast, and reserved IPs
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return False
        
    # Block specific cloud metadata IPs that might not be caught by standard private checks
    # AWS/GCP/Azure metadata: 169.254.169.254 (link-local covers this, but explicit is better)
    if str(ip) == "169.254.169.254":
        return False
        
    return True

class UrlValidator:
    ALLOWED_SCHEMES = {"http", "https"}
    
    @classmethod
    def validate_and_resolve(cls, url: str) -> str:
        """
        Validates a URL against SSRF and embedded credentials.
        Resolves the hostname to an IP and verifies the IP is public.
        Raises SSRFViolationError if unsafe.
        Returns the original URL if safe.
        """
        try:
            parsed = urllib.parse.urlparse(url)
        except Exception as e:
            raise SSRFViolationError(f"Malformed URL: {e}")

        if parsed.scheme.lower() not in cls.ALLOWED_SCHEMES:
            raise SSRFViolationError(f"Unsupported scheme: {parsed.scheme}")

        if parsed.username or parsed.password:
            raise SSRFViolationError("Credentials embedded in URL are not allowed")

        hostname = parsed.hostname
        if not hostname:
            raise SSRFViolationError("Missing hostname in URL")

        # Basic string checks for common metadata hostnames
        forbidden_hosts = {"localhost", "metadata.google.internal", "instance-data", "169.254.169.254"}
        if hostname.lower() in forbidden_hosts:
            raise SSRFViolationError(f"Forbidden hostname: {hostname}")

        # Block dangerous ports (e.g. 22 SSH, 6379 Redis, etc. - anything other than 80, 443, 8080)
        allowed_ports = {80, 443, 8080, 8443}
        if parsed.port and parsed.port not in allowed_ports:
            raise SSRFViolationError(f"Dangerous port specified: {parsed.port}")

        # Resolve DNS
        try:
            # getaddrinfo handles both IPv4 and IPv6
            addrs = socket.getaddrinfo(hostname, None)
            resolved_ips = [info[4][0] for info in addrs]
        except socket.gaierror as e:
            raise SSRFViolationError(f"DNS resolution failed for {hostname}: {e}")

        if not resolved_ips:
            raise SSRFViolationError(f"No IPs resolved for {hostname}")

        # Ensure ALL resolved IPs are safe. (DNS rebinding protection part 1)
        # If a hostname resolves to both a public and a private IP, we block it.
        for ip in resolved_ips:
            if not is_safe_ip(ip):
                raise SSRFViolationError(f"Hostname {hostname} resolved to unsafe IP: {ip}")

        # For TOCTOU protection, we return the first safe IP alongside the URL
        # so the caller can pin the DNS resolution.
        safe_ip = resolved_ips[0]
        return url, safe_ip

from fastapi import Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import get_db
from app.database.models import Profile

async def get_valid_profile(request: Request, db: AsyncSession = Depends(get_db)) -> Profile:
    profile_id = request.headers.get("x-profile-id")
    if not profile_id:
        raise HTTPException(status_code=400, detail="Missing X-Profile-ID header")
    
    profile = await db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found or invalid X-Profile-ID")
        
    return profile


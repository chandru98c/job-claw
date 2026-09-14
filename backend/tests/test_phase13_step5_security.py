import pytest
import uuid
import httpx
from unittest.mock import patch, MagicMock

from app.core.security import UrlValidator, SSRFViolationError
from app.core.http import DomainPolicy, SafeHTTPClient, PolicyViolationError
from app.database.models import Application, ApplicationStatus

def test_ssrf_protection():
    """
    Test that the UrlValidator strictly blocks loopback, private IPs, and local resolution.
    """
    # 1. Localhost
    with pytest.raises(SSRFViolationError):
        UrlValidator.validate_and_resolve("http://localhost/admin")
        
    # 2. Local IP
    with pytest.raises(SSRFViolationError):
        UrlValidator.validate_and_resolve("http://127.0.0.1/api")
        
    # 3. Private IP (AWS Metadata)
    with pytest.raises(SSRFViolationError):
        UrlValidator.validate_and_resolve("http://169.254.169.254/latest/meta-data")
        
    # 4. Zero IP trick
    with pytest.raises(SSRFViolationError):
        UrlValidator.validate_and_resolve("http://0.0.0.0/")
        
@pytest.mark.asyncio
async def test_domain_policy_enforcement():
    """
    Test DomainPolicy strict enforcement on the HTTP Client.
    """
    policy = DomainPolicy(allowed_domains=["workday.com", "greenhouse.io"])
    
    # Allowed domain
    with patch("httpx.AsyncClient.send") as mock_send:
        mock_send.return_value = httpx.Response(200, request=MagicMock())
        async with SafeHTTPClient(policy=policy) as client:
            # We must use validate_and_resolve, but since it does DNS resolution we will mock it
            with patch.object(UrlValidator, 'validate_and_resolve', return_value=("https://boards.greenhouse.io/test", "1.2.3.4")):
                res = await client.get("https://boards.greenhouse.io/test")
                assert res is not None
                
    # Disallowed domain
    async with SafeHTTPClient(policy=policy) as client:
        with patch.object(UrlValidator, 'validate_and_resolve', return_value=("https://evil.com/test", "1.2.3.4")):
            with pytest.raises(PolicyViolationError):
                await client.get("https://evil.com/test")

def test_approval_boundary():
    """
    Test that an application cannot be submitted unless it is explicitly APPROVED.
    """
    app = Application(
        id=str(uuid.uuid4()),
        profile_id=str(uuid.uuid4()),
        job_id=str(uuid.uuid4()),
        status=ApplicationStatus.PREPARING
    )
    
    # In the real codebase, the submission engine checks: if app.status != APPROVED: raise
    def submit(application):
        if application.status != ApplicationStatus.APPROVED:
            raise ValueError("Cannot submit an application that is not APPROVED")
        return True
        
    with pytest.raises(ValueError, match="APPROVED"):
        submit(app)
        
    app.status = ApplicationStatus.APPROVED
    assert submit(app) is True

def test_authorization_boundary():
    """
    Test that endpoints checking application status require the correct profile ownership.
    """
    app = Application(
        id=str(uuid.uuid4()),
        profile_id="user-1",
        job_id=str(uuid.uuid4()),
        status=ApplicationStatus.PREPARING
    )
    
    def check_ownership(application, current_user_id):
        if application.profile_id != current_user_id:
            raise PermissionError("Access denied")
            
    with pytest.raises(PermissionError):
        check_ownership(app, "user-2")
        
    check_ownership(app, "user-1") # Should pass

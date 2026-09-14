import pytest
import httpx
from unittest import mock
from app.core.http import SafeHTTPClient, DomainPolicy, PolicyViolationError
from app.core.security import SSRFViolationError
import socket

@pytest.mark.asyncio
async def test_tls_verification_enabled():
    with mock.patch("app.core.http.httpx.AsyncClient") as mock_client:
        SafeHTTPClient()
        # Verify that httpx.AsyncClient was initialized with verify=True
        mock_client.assert_called_once()
        assert mock_client.call_args.kwargs.get("verify") is True

@pytest.mark.asyncio
async def test_redirect_to_private_rejected():
    """
    Test that if a public URL redirects to a private IP (e.g. localhost),
    the redirect hop is validated and blocked BEFORE fetching.
    """
    policy = DomainPolicy(max_redirects=3)
    
    # Mock DNS resolution: first hop public, second hop local
    def mock_dns(hostname, *args, **kwargs):
        if hostname == "public.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]
        if hostname == "localhost":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
        return []

    # Mock httpx response for public.com to return a redirect to localhost
    class MockResponse:
        status_code = 302
        headers = {"Location": "http://localhost/admin"}
        def raise_for_status(self): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass

    class MockStreamContext:
        async def __aenter__(self): return MockResponse()
        async def __aexit__(self, *args): pass

    with mock.patch("app.core.security._original_getaddrinfo", side_effect=mock_dns):
        with mock.patch("httpx.AsyncClient.stream", return_value=MockStreamContext()):
            client = SafeHTTPClient(policy)
            with pytest.raises(SSRFViolationError, match="Forbidden hostname: localhost"):
                await client.get("http://public.com")

@pytest.mark.asyncio
async def test_max_response_size_enforced():
    policy = DomainPolicy(max_response_bytes=10) # very small limit
    
    # Mock DNS
    with mock.patch("app.core.security._original_getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]):
        class MockResponse:
            status_code = 200
            headers = {}
            def raise_for_status(self): pass
            async def aiter_bytes(self):
                yield b"123456"
                yield b"789012" # total 12 bytes > 10

        class MockStreamContext:
            async def __aenter__(self): return MockResponse()
            async def __aexit__(self, *args): pass

        with mock.patch("httpx.AsyncClient.stream", return_value=MockStreamContext()):
            client = SafeHTTPClient(policy)
            with pytest.raises(PolicyViolationError, match="exceeded maximum allowed size"):
                await client.get("http://example.com")

@pytest.mark.asyncio
async def test_max_retries_and_backoff():
    policy = DomainPolicy(max_retries=2)
    
    with mock.patch("app.core.security._original_getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]):
        with mock.patch("httpx.AsyncClient.stream", side_effect=httpx.RequestError("Network error")):
            with mock.patch("asyncio.sleep", new_callable=mock.AsyncMock) as mock_sleep:
                client = SafeHTTPClient(policy)
                with pytest.raises(httpx.RequestError):
                    await client.get("http://example.com")
                
                # Should have slept for exponential backoff: 2^0 = 1, 2^1 = 2
                assert mock_sleep.call_count == 2
                mock_sleep.assert_any_call(1)
                mock_sleep.assert_any_call(2)

@pytest.mark.asyncio
async def test_domain_policy_enforcement():
    policy = DomainPolicy(allowed_domains=["example.com"])
    
    with mock.patch("app.core.security._original_getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]):
        client = SafeHTTPClient(policy)
        # allowed
        with mock.patch("httpx.AsyncClient.stream") as mock_stream:
            # We just need to mock the response iteration safely
            class MockResponse:
                status_code = 200
                headers = {}
                def raise_for_status(self): pass
                async def aiter_bytes(self): yield b"ok"
            class MockStreamContext:
                async def __aenter__(self): return MockResponse()
                async def __aexit__(self, *args): pass
            mock_stream.return_value = MockStreamContext()
            
            await client.get("http://example.com") # Should pass
            await client.get("http://sub.example.com") # Should pass
            
            # Not allowed
            with pytest.raises(PolicyViolationError, match="is not in the allowed list"):
                await client.get("http://malicious.com")

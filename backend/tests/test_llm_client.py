import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pydantic import BaseModel
import json

from app.core.config import settings
from app.core.llm import (
    LLMClient,
    GroqProvider,
    GeminiProvider,
    LLMError,
    LLMAuthError,
    LLMRateLimitError,
    LLMTransientError,
    LLMMalformedOutputError
)

class DummySchema(BaseModel):
    message: str
    score: int

@pytest.fixture
def mock_settings(monkeypatch):
    monkeypatch.setattr(settings, "LLM_SEQUENCE", "GROQ,GEMINI")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test_groq_key")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test_gemini_key")
    return settings

@pytest.fixture
def llm_client(mock_settings):
    # This initializes a client fresh with the mocked settings
    return LLMClient()

@pytest.mark.asyncio
async def test_llm_client_initialization(mock_settings):
    client = LLMClient()
    assert len(client.sequence) == 2
    assert client.sequence[0].name == "GROQ"
    assert client.sequence[1].name == "GEMINI"
    
@pytest.mark.asyncio
async def test_groq_success(llm_client):
    # Mock Groq provider so it returns success
    with patch.object(llm_client.sequence[0], 'generate_structured', new_callable=AsyncMock) as mock_groq:
        mock_groq.return_value = DummySchema(message="groq_success", score=100)
        
        result = await llm_client.generate_structured("test prompt", DummySchema)
        
        mock_groq.assert_called_once()
        assert result.message == "groq_success"

@pytest.mark.asyncio
async def test_fallback_on_rate_limit(llm_client):
    # Mock Groq to throw rate limit error, and Gemini to succeed
    with patch.object(llm_client.sequence[0], 'generate_structured', new_callable=AsyncMock) as mock_groq:
        with patch.object(llm_client.sequence[1], 'generate_structured', new_callable=AsyncMock) as mock_gemini:
            
            mock_groq.side_effect = LLMRateLimitError("429 Too Many Requests")
            mock_gemini.return_value = DummySchema(message="gemini_success", score=90)
            
            result = await llm_client.generate_structured("test prompt", DummySchema)
            
            mock_groq.assert_called_once()
            mock_gemini.assert_called_once()
            assert result.message == "gemini_success"

@pytest.mark.asyncio
async def test_fallback_on_transient_error(llm_client):
    # Mock Groq to throw transient error (e.g. 503)
    with patch.object(llm_client.sequence[0], 'generate_structured', new_callable=AsyncMock) as mock_groq:
        with patch.object(llm_client.sequence[1], 'generate_structured', new_callable=AsyncMock) as mock_gemini:
            
            mock_groq.side_effect = LLMTransientError("503 Service Unavailable")
            mock_gemini.return_value = DummySchema(message="gemini_success", score=90)
            
            result = await llm_client.generate_structured("test prompt", DummySchema)
            
            mock_groq.assert_called_once()
            mock_gemini.assert_called_once()
            assert result.message == "gemini_success"

@pytest.mark.asyncio
async def test_auth_error_fallback(llm_client):
    # If Groq has an auth error, we STILL fallback to Gemini because Gemini might be correctly configured
    with patch.object(llm_client.sequence[0], 'generate_structured', new_callable=AsyncMock) as mock_groq:
        with patch.object(llm_client.sequence[1], 'generate_structured', new_callable=AsyncMock) as mock_gemini:
            
            mock_groq.side_effect = LLMAuthError("Invalid API Key")
            mock_gemini.return_value = DummySchema(message="gemini_success", score=90)
            
            result = await llm_client.generate_structured("test prompt", DummySchema)
            
            mock_groq.assert_called_once()
            mock_gemini.assert_called_once()
            assert result.message == "gemini_success"

@pytest.mark.asyncio
async def test_all_providers_fail(llm_client):
    with patch.object(llm_client.sequence[0], 'generate_structured', new_callable=AsyncMock) as mock_groq:
        with patch.object(llm_client.sequence[1], 'generate_structured', new_callable=AsyncMock) as mock_gemini:
            
            mock_groq.side_effect = LLMRateLimitError("Groq 429")
            mock_gemini.side_effect = LLMTransientError("Gemini 500")
            
            with pytest.raises(LLMError, match="All providers in sequence failed"):
                await llm_client.generate_structured("test prompt", DummySchema)
            
            mock_groq.assert_called_once()
            mock_gemini.assert_called_once()

@pytest.mark.asyncio
async def test_malformed_output_fallback(llm_client):
    with patch.object(llm_client.sequence[0], 'generate_structured', new_callable=AsyncMock) as mock_groq:
        with patch.object(llm_client.sequence[1], 'generate_structured', new_callable=AsyncMock) as mock_gemini:
            
            # Groq gives bad JSON
            mock_groq.side_effect = LLMMalformedOutputError("Failed to parse JSON")
            mock_gemini.return_value = DummySchema(message="gemini_success", score=90)
            
            result = await llm_client.generate_structured("test prompt", DummySchema)
            
            mock_groq.assert_called_once()
            mock_gemini.assert_called_once()
            assert result.message == "gemini_success"

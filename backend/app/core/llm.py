import json
import logging
import asyncio
from typing import Any, Dict, List, Type, TypeVar, Callable, Awaitable
from abc import ABC, abstractmethod
from pydantic import BaseModel, ValidationError

# Gemini library imports
import google.generativeai as genai
from google.generativeai.types import generation_types

# Groq library imports
from groq import AsyncGroq
import groq

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# --- Error Classifications ---
class LLMError(Exception):
    """Base exception for LLM-related errors."""
    pass

class LLMAuthError(LLMError):
    """Authentication or configuration error. Should not trigger fallback retry on the same provider."""
    pass

class LLMRateLimitError(LLMError):
    """Rate limit (429) encountered. Safe to trigger fallback."""
    pass

class LLMTransientError(LLMError):
    """Server error (5xx) or timeout. Safe to trigger fallback."""
    pass

class LLMMalformedOutputError(LLMError):
    """Model responded, but the output violated the requested structured format/schema."""
    pass


# --- Provider Abstraction ---
class LLMProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def generate_structured(self, prompt: str, schema: Type[T], timeout: int = 30) -> T:
        """
        Generate a structured response adhering to the given Pydantic schema.
        Must raise LLMAuthError, LLMRateLimitError, LLMTransientError, or LLMMalformedOutputError
        for appropriate sequence fallback handling.
        """
        pass

# --- Groq Implementation ---
class GroqProvider(LLMProvider):
    def __init__(self):
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not configured.")
        self.client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        self.model = settings.GROQ_MODEL

    @property
    def name(self) -> str:
        return "GROQ"

    async def generate_structured(self, prompt: str, schema: Type[T], timeout: int = 30) -> T:
        try:
            schema_str = json.dumps(schema.model_json_schema())
            system_prompt = f"Return ONLY a valid JSON object matching this JSON schema: {schema_str}"
            
            # We enforce JSON object response format
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0
                ),
                timeout=timeout
            )
            
            content = response.choices[0].message.content
            if not content:
                raise LLMMalformedOutputError("Groq returned empty content.")
            
            # Validate against Pydantic schema
            try:
                data = json.loads(content)
                return schema.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as e:
                raise LLMMalformedOutputError(f"Groq output failed validation: {e}")

        except asyncio.TimeoutError:
            raise LLMTransientError(f"Groq request timed out after {timeout}s.")
        except groq.AuthenticationError as e:
            raise LLMAuthError(f"Groq authentication failed: {e}")
        except groq.NotFoundError as e:
            raise LLMAuthError(f"Groq configuration error (model not found): {e}")
        except groq.BadRequestError as e:
            raise LLMAuthError(f"Groq configuration error (bad request / model decommissioned): {e}")
        except groq.RateLimitError as e:
            raise LLMRateLimitError(f"Groq rate limit exceeded: {e}")
        except (groq.APIConnectionError, groq.InternalServerError, groq.APIError) as e:
            raise LLMTransientError(f"Groq transient error: {e}")
        except Exception as e:
            # Wrap unexpected SDK errors
            if isinstance(e, (LLMAuthError, LLMRateLimitError, LLMTransientError, LLMMalformedOutputError)):
                raise e
            raise LLMTransientError(f"Unexpected Groq error: {e}")


# --- Gemini Implementation ---
class GeminiProvider(LLMProvider):
    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured.")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        # Gemini 1.5 Pro or Flash supports JSON response mime_type
        self.model = genai.GenerativeModel(settings.GEMINI_MODEL)

    @property
    def name(self) -> str:
        return "GEMINI"

    async def generate_structured(self, prompt: str, schema: Type[T], timeout: int = 30) -> T:
        try:
            schema_str = json.dumps(schema.model_json_schema())
            full_prompt = f"{prompt}\n\nReturn ONLY a valid JSON object matching this exact JSON schema: {schema_str}"
            
            # Note: We enforce JSON generation via config
            generation_config = genai.types.GenerationConfig(
                temperature=0.0,
                response_mime_type="application/json"
            )
            
            response = await asyncio.wait_for(
                self.model.generate_content_async(
                    full_prompt,
                    generation_config=generation_config
                ),
                timeout=timeout
            )
            
            content = response.text
            if not content:
                raise LLMMalformedOutputError("Gemini returned empty content.")
                
            try:
                data = json.loads(content)
                return schema.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as e:
                raise LLMMalformedOutputError(f"Gemini output failed validation: {e}")

        except asyncio.TimeoutError:
            raise LLMTransientError(f"Gemini request timed out after {timeout}s.")
        except Exception as e:
            # Google SDK errors can be generic, map based on string heuristics or specific types if available
            err_str = str(e).lower()
            if "api_key" in err_str or "unauthenticated" in err_str or "forbidden" in err_str:
                raise LLMAuthError(f"Gemini auth error: {e}")
            if "quota" in err_str or "429" in err_str or "exhausted" in err_str:
                raise LLMRateLimitError(f"Gemini rate limit: {e}")
            
            if isinstance(e, (LLMAuthError, LLMRateLimitError, LLMTransientError, LLMMalformedOutputError)):
                raise e
                
            raise LLMTransientError(f"Gemini transient/server error: {e}")


# --- Sequence Engine / Client ---
class LLMClient:
    """
    Centralized client that wraps multiple LLMProviders and executes fallback policy.
    Callers depend on this, not on Groq/Gemini SDKs.
    """
    def __init__(self):
        self.sequence: List[LLMProvider] = []
        self._initialize_sequence()

    def _initialize_sequence(self):
        sequence_names = [s.strip().upper() for s in settings.LLM_SEQUENCE.split(",") if s.strip()]
        
        for name in sequence_names:
            try:
                if name == "GROQ":
                    self.sequence.append(GroqProvider())
                elif name == "GEMINI":
                    self.sequence.append(GeminiProvider())
                else:
                    logger.warning(f"Unknown LLM provider in sequence: {name}")
            except ValueError as e:
                # e.g., missing API keys
                logger.warning(f"Skipping provider {name} due to initialization error: {e}")
                
        if not self.sequence:
            logger.error("No valid LLM providers initialized. LLM operations will fail.")

    async def generate_structured(self, prompt: str, schema: Type[T], timeout: int = 30) -> T:
        """
        Iterates through the configured LLM sequence until a valid structured response is produced.
        Classifies errors to determine if fallback is appropriate.
        """
        if not self.sequence:
            raise LLMError("No LLM providers available (check API keys and LLM_SEQUENCE config).")

        last_error = None
        
        for provider in self.sequence:
            try:
                logger.debug(f"Attempting LLM generation via {provider.name}")
                result = await provider.generate_structured(prompt, schema, timeout=timeout)
                return result
                
            except (LLMRateLimitError, LLMTransientError, LLMMalformedOutputError) as e:
                # These are safe to fallback
                logger.warning(f"Provider {provider.name} failed (safe fallback): {e}")
                last_error = e
                continue
                
            except LLMAuthError as e:
                # Auth error means misconfiguration. We can fallback to the next provider,
                # because the next provider might be correctly configured.
                logger.warning(f"Provider {provider.name} auth failed (attempting fallback to next provider): {e}")
                last_error = e
                continue
                
            except Exception as e:
                # Unknown exceptions also fallback, but logged as error
                logger.error(f"Provider {provider.name} failed with unknown error: {e}")
                last_error = e
                continue

        # If we exhausted the sequence, raise the last error
        raise LLMError(f"All providers in sequence failed. Last error: {str(last_error)}")

# Singleton instance to be used across the app
llm_client = LLMClient()

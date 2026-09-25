import asyncio
import logging
from pydantic import BaseModel, Field

# Ensure settings are loaded
from app.core.config import settings

# Override sequence for smoke test to test both
settings.LLM_SEQUENCE = "GROQ,GEMINI"

from app.core.llm import llm_client, GroqProvider, GeminiProvider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestSchema(BaseModel):
    is_working: bool = Field(..., description="Set to true if you are reading this prompt")
    provider_name: str = Field(..., description="The name of the LLM provider you are generating this from")
    reasoning: str = Field(..., description="Brief explanation")

async def test_provider(provider, name):
    logger.info(f"\n--- Testing {name} ---")
    try:
        result = await provider.generate_structured(
            prompt="You are an LLM test script. Follow the schema constraints.",
            schema=TestSchema,
            timeout=10
        )
        logger.info(f"SUCCESS: {result.model_dump_json(indent=2)}")
        return True
    except Exception as e:
        logger.error(f"FAILED: {type(e).__name__} - {e}")
        return False

async def main():
    logger.info(f"Loaded Settings: GROQ_KEY={'Yes' if settings.GROQ_API_KEY else 'No'}, GEMINI_KEY={'Yes' if settings.GEMINI_API_KEY else 'No'}")
    
    groq_p = GroqProvider()
    gemini_p = GeminiProvider()
    
    groq_ok = await test_provider(groq_p, "GROQ")
    gemini_ok = await test_provider(gemini_p, "GEMINI")
    
    logger.info("\n--- Testing Sequence Fallback ---")
    try:
        # Will use Groq first, then Gemini if Groq fails
        result = await llm_client.generate_structured(
            prompt="You are testing the fallback sequencer.",
            schema=TestSchema
        )
        logger.info(f"SEQUENCE SUCCESS: {result.model_dump_json(indent=2)}")
    except Exception as e:
        logger.error(f"SEQUENCE FAILED: {type(e).__name__} - {e}")

if __name__ == "__main__":
    asyncio.run(main())

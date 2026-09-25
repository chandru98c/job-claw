from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/jobclaw"
    
    # Redis / ARQ
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Worker Settings
    WORKER_CONCURRENCY: int = 10
    WORKER_MAX_TRIES: int = 3
    WORKER_JOB_TIMEOUT: int = 300 # 5 minutes

    # LLM Integration
    GROQ_API_KEY: str | None = None
    GROQ_MODEL: str = "llama3-8b-8192"
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    
    # Comma-separated list of providers to try (e.g., "GROQ,GEMINI")
    LLM_SEQUENCE: str = "GROQ,GEMINI"

    # Semantic Search Configuration
    ENABLE_SEMANTIC_SEARCH: bool = True
    MAX_SEMANTIC_CANDIDATES: int = 20
    
    # Testing Flag
    TESTING: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

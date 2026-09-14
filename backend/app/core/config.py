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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

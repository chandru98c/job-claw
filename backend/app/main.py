import logging
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import tasks, sse, system, jobs, sources, engines, applications, mock_ats, saved_searches, recommendations, profiles
from app.core.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup ARQ Redis Pool (graceful fallback if Redis is temporarily unavailable)
    app.state.redis = None
    try:
        app.state.redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        logger.info("Redis pool initialized")
    except Exception as exc:
        logger.warning("Redis pool unavailable at startup: %s", exc)

    yield

    # Cleanup ARQ Redis Pool
    redis = getattr(app.state, "redis", None)
    if redis is not None:
        await redis.aclose()


app = FastAPI(
    title="Job-Claw API",
    description="Enterprise-grade autonomous job discovery and extraction engine.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "job-claw-backend"}


app.include_router(tasks.router)
app.include_router(sse.router)
app.include_router(system.router)
app.include_router(jobs.router)
app.include_router(sources.router)
app.include_router(engines.router)
app.include_router(applications.router)
app.include_router(mock_ats.router)
app.include_router(saved_searches.router)
app.include_router(recommendations.router)
app.include_router(profiles.router)

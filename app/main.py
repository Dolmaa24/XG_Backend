import logging
import json
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.database import init_db
from app.services.parser import load_spacy_model
from app.services.matcher import load_embedding_model
from app.api.v1 import auth, jobs, resume, match, interview, ranking
from app.schemas.schemas import HealthResponse

# ── JSON structured logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": %(message)s}',
)
logger = logging.getLogger(__name__)

# ── Rate limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


# ── Lifespan: startup / shutdown ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info({"event": "startup_begin"})

    # Initialise DB tables
    await init_db()

    # Pre-load NLP models so first request is not slow
    load_spacy_model()
    load_embedding_model()

    logger.info({"event": "startup_complete"})
    yield

    logger.info({"event": "shutdown"})


# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI HR Recruitment Simulator — Backend API",
    description="REST API for automated resume parsing, job matching, AI interviews, and candidate ranking.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else ["https://your-frontend.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global exception handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error({"event": "unhandled_exception", "error": str(exc), "path": request.url.path})
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error", "detail": str(exc) if settings.DEBUG else "Contact support"},
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(resume.router, prefix="/api/v1")
app.include_router(match.router, prefix="/api/v1")
app.include_router(interview.router, prefix="/api/v1")
app.include_router(ranking.router, prefix="/api/v1")


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal

    # DB check
    db_status = "disconnected"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        logger.error({"event": "health_db_fail", "error": str(e)})

    # Redis check
    redis_status = "disconnected"
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        redis_status = "connected"
    except Exception as e:
        logger.error({"event": "health_redis_fail", "error": str(e)})

    return HealthResponse(
        status="ok" if db_status == "connected" and redis_status == "connected" else "degraded",
        db=db_status,
        redis=redis_status,
    )


@app.get("/", include_in_schema=False)
async def root():
    return {"message": "AI HR Recruitment Simulator API", "docs": "/docs"}

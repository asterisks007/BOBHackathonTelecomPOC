"""
FastAPI application entrypoint.

Security: CORS is restricted to configured allowed origins (never wildcard in production).
All routes are versioned under /api/v1. Swagger docs are enabled for demo purposes.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.models import HealthResponse, ServiceStatus
from api.routes import router as api_router
from api.watson_routes import router as watson_router
from core.config import get_settings
from core.granite_client import GraniteClient

logger = logging.getLogger(__name__)

# ── Application lifespan ──────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle handler."""
    settings = get_settings()
    logger.info(
        "Telecom BOB starting | use_mock=%s | port=%s",
        settings.use_mock,
        settings.api_port,
    )
    if not settings.use_mock:
        missing = settings.validate_live_credentials()
        if missing:
            logger.error("Missing live credentials: %s", missing)
    yield
    logger.info("Telecom BOB shutting down.")


# ── App instantiation ─────────────────────────────────────────────────────────

settings = get_settings()

app = FastAPI(
    title="Telecom Outage Resolution BOB",
    description=(
        "7-agent agentic AI system for telecom outage resolution. "
        "IBM BOB Hackathon 2026 POC."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS — restricted, NOT wildcard ──────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)

# ── Register API routes ───────────────────────────────────────────────────────
app.include_router(api_router)
app.include_router(watson_router)

# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/", tags=["info"], summary="Application info")
async def root() -> JSONResponse:
    """Return basic application metadata."""
    return JSONResponse(
        {
            "name": "Telecom Outage Resolution BOB",
            "version": "0.1.0",
            "event": "IBM BOB Hackathon 2026",
            "status": "running",
            "use_mock": settings.use_mock,
            "docs": "/docs",
        }
    )


@app.get("/health", response_model=HealthResponse, tags=["info"], summary="Health check")
async def health() -> HealthResponse:
    """
    Return system health and dependency status.

    The api_calls_used field tracks real IBM API calls consumed against the
    100-call/month Lite Plan budget.
    """
    services = [
        ServiceStatus(
            name="watsonx.ai",
            status="ok" if settings.use_mock else "unknown",
            mock_mode=settings.use_mock,
        ),
        ServiceStatus(
            name="IBM NLU",
            status="ok" if settings.use_mock else "unknown",
            mock_mode=settings.use_mock,
        ),
        ServiceStatus(
            name="Cloudant",
            status="ok" if settings.use_mock else "unknown",
            mock_mode=settings.use_mock,
        ),
        ServiceStatus(
            name="ChromaDB",
            status="ok",
            mock_mode=False,
        ),
    ]

    return HealthResponse(
        status="ok",
        version="0.1.0",
        use_mock=settings.use_mock,
        services=services,
        api_calls_used=GraniteClient.get_real_call_count(),
        api_calls_budget=100,
    )


@app.get("/ready", tags=["info"], summary="Readiness probe")
async def ready() -> JSONResponse:
    """Kubernetes/cloud readiness probe — returns 200 when app can serve traffic."""
    return JSONResponse({"ready": True})

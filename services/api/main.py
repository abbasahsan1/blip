"""
main.py — Blipps v1 FastAPI entry point.

Lifespan tasks (startup/shutdown):
  1. Create DB tables (create_all via asyncpg)
  2. Ping Neon Postgres — log result
  3. Open Redis connection (if REDIS_URL provided) — log success/failure
  4. Close Redis connection on shutdown

Port binding:
  Render injects a PORT env var at runtime. The CMD in the Dockerfile
  reads it via a shell-form invocation so the app always binds to
  whatever port Render assigns. Locally, PORT defaults to 8000.

Run locally:
  cd ~/Desktop/Blipp-new
  uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
import logging
import os
import uuid
from contextlib import asynccontextmanager
from dotenv import load_dotenv

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from database import AsyncSessionLocal, create_db_and_tables
from routes import router

load_dotenv()

log = logging.getLogger("blipps")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")

# ---------------------------------------------------------------------------
# Lifespan: startup + shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Postgres ──────────────────────────────────────────────────────────
    log.info("Creating DB tables if needed…")
    try:
        await create_db_and_tables()
        log.info("✓ Postgres tables verified/ready")
    except Exception as exc:
        log.error("✗ Postgres setup failed: %s", exc)

    # ── Redis (connectivity check only — NOT used for anything yet) ───────
    redis_url = os.getenv("REDIS_URL", "").strip()
    redis_client = None
    if redis_url:
        try:
            redis_client = aioredis.from_url(redis_url, decode_responses=True)
            pong = await redis_client.ping()
            log.info("✓ Redis connected — PING -> %s (unused until caching step)", pong)
            app.state.redis = redis_client
        except Exception as exc:
            log.warning("✗ Redis connection failed: %s — continuing without Redis", exc)
            app.state.redis = None
    else:
        log.info("ℹ REDIS_URL not set — Redis connectivity check skipped")
        app.state.redis = None

    yield  # app is running

    # ── Shutdown ──────────────────────────────────────────────────────────
    if redis_client:
        await redis_client.aclose()
        log.info("Redis connection closed")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Blipps API",
    version="1.0.0",
    description="Audio-only short-form content — v1 single-service backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Error handlers — enforce { "error": { "code", "message", "request_id" } }
# ---------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        content = detail
    else:
        content = {
            "error": {
                "code": str(exc.status_code),
                "message": str(detail),
                "request_id": request.headers.get("x-request-id", str(uuid.uuid4())),
            }
        }
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": str(exc.errors()),
                "request_id": request.headers.get("x-request-id", str(uuid.uuid4())),
            }
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "request_id": request.headers.get("x-request-id", str(uuid.uuid4())),
            }
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.include_router(router)


# ---------------------------------------------------------------------------
# /healthz — liveness + dependency status
# ---------------------------------------------------------------------------

@app.get("/healthz", tags=["ops"])
async def healthz(request: Request):
    results: dict[str, str] = {}

    # Postgres check
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        results["postgres"] = "ok"
    except Exception as exc:
        results["postgres"] = f"error: {exc}"

    # Redis check
    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        try:
            await redis.ping()
            results["redis"] = "ok"
        except Exception as exc:
            results["redis"] = f"error: {exc}"
    else:
        results["redis"] = "not_configured"

    overall = "ok" if results["postgres"] == "ok" and results["redis"] in ("ok", "not_configured") else "degraded"
    return {"status": overall, **results}

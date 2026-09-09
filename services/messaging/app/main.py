import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from blipp_common.config import settings
from blipp_common.database import close_db_pool, get_db_pool, init_db_pool
from blipp_common.events import event_bus
from blipp_common.exceptions import (
    AppException,
    CODE_FORBIDDEN,
    CODE_INTERNAL_SERVER_ERROR,
    CODE_NOT_FOUND,
    CODE_UNAUTHORIZED,
    CODE_VALIDATION_ERROR,
)
from blipp_common.storage import storage_service
from app.api.v1.messages import router as messages_router
from app.api.v1.stories import router as stories_router
from app.models.messaging import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("messaging.main")

_cleanup_stop_event = asyncio.Event()


# ─── Background Story Expiration Worker (§8) ───────────────────────────────────

async def cleanup_expired_stories() -> int:
    """
    Executes background story expiration:
    1. Selects expired stories (expires_at <= NOW())
    2. Deletes underlying audio files from MinIO / S3 storage
    3. Deletes story rows from the database
    """
    pool = await get_db_pool()
    if not pool:
        logger.warning("DB pool unavailable for story cleanup worker")
        return 0

    try:
        async with pool.acquire() as conn:
            expired_rows = await conn.fetch(
                """
                SELECT story_id, audio_url
                FROM stories
                WHERE expires_at <= NOW()
                """
            )
            if not expired_rows:
                return 0

            logger.info(f"Found {len(expired_rows)} expired stories to delete")
            bucket = getattr(settings, "S3_BUCKET_STORIES", "blipp-stories") or "blipp-stories"
            for row in expired_rows:
                audio_url = row["audio_url"]
                try:
                    await storage_service.delete_file(
                        storage_key=audio_url,
                        bucket_name=bucket,
                    )
                except Exception as e:
                    logger.warning(f"Failed to delete story audio file {audio_url}: {e}")

            res = await conn.execute(
                """
                DELETE FROM stories
                WHERE expires_at <= NOW()
                """
            )
            logger.info(f"Expired stories DB purge completed: {res}")
            return len(expired_rows)
    except Exception as e:
        logger.error(f"Error during expired stories cleanup: {e}", exc_info=True)
        return 0


async def run_story_cleanup_loop(stop_event: asyncio.Event, interval_seconds: int = 600):
    """
    Periodic background loop running every 10 minutes (600 seconds) to clean up expired stories.
    """
    logger.info(f"Starting ephemeral story expiration background task (interval: {interval_seconds}s)")
    while not stop_event.is_set():
        try:
            await cleanup_expired_stories()
        except Exception as e:
            logger.error(f"Unexpected error in story cleanup task: {e}")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass


# ─── Application Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting Blipp Messaging & Stories Service v{settings.APP_VERSION}")
    try:
        await init_db_pool()
        logger.info("Database connection pool initialized")
    except Exception as e:
        logger.error(f"Database pool startup error: {e}")

    try:
        await event_bus.connect(client_name="messaging-service")
        logger.info("Connected to NATS JetStream Event Bus")
    except Exception as e:
        logger.warning(f"NATS startup connection warning: {e}")

    # Ensure MinIO bucket for stories exists
    try:
        bucket = getattr(settings, "S3_BUCKET_STORIES", "blipp-stories") or "blipp-stories"
        client = storage_service.internal_s3_client or storage_service.s3_client
        if storage_service.use_s3 and client:
            try:
                client.head_bucket(Bucket=bucket)
            except Exception:
                client.create_bucket(Bucket=bucket)
                logger.info(f"Ensured bucket '{bucket}' exists")
    except Exception as e:
        logger.warning(f"Bucket check note: {e}")

    # Start 10-minute async story expiration background worker
    _cleanup_stop_event.clear()
    cleanup_task = asyncio.create_task(run_story_cleanup_loop(_cleanup_stop_event, interval_seconds=600))

    yield

    logger.info("Stopping story expiration task and shutting down...")
    _cleanup_stop_event.set()
    cleanup_task.cancel()
    await asyncio.gather(cleanup_task, return_exceptions=True)

    try:
        await event_bus.close()
    except Exception as e:
        logger.warning(f"Event bus shutdown note: {e}")

    try:
        await close_db_pool()
    except Exception as e:
        logger.warning(f"Database pool shutdown note: {e}")

    logger.info("Shutting down Blipp Messaging & Stories Service")


# ─── FastAPI Initialization ───────────────────────────────────────────────────

app = FastAPI(
    title="Blipp Messaging & Stories Service",
    description="Dedicated microservice for Direct Messaging and 24-Hour Ephemeral Audio Stories (§3 #4, §5.4)",
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


# ─── Request ID Middleware ───────────────────────────────────────────────────

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(RequestIDMiddleware)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Standardized Exception Handlers ──────────────────────────────────────────

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        loc = " -> ".join(str(p) for p in err.get("loc", []))
        errors.append({"field": loc, "message": err.get("msg", "Invalid value")})

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "code": CODE_VALIDATION_ERROR,
            "message": "Validation error in request parameters",
            "details": {"validation_errors": errors},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
    code_map = {
        401: CODE_UNAUTHORIZED,
        403: CODE_FORBIDDEN,
        404: CODE_NOT_FOUND,
    }
    error_code = code_map.get(exc.status_code, CODE_INTERNAL_SERVER_ERROR)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": error_code,
            "message": str(exc.detail),
            "details": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": CODE_INTERNAL_SERVER_ERROR,
            "message": "Internal server error occurred",
            "details": {},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/docs", include_in_schema=False)
async def docs_redirect():
    return RedirectResponse(url="/api/docs")


# Mount routes under /v1 (standard) and /api (backward compatibility)
app.include_router(messages_router, prefix="/v1")
app.include_router(stories_router, prefix="/v1")
app.include_router(messages_router, prefix="/api")
app.include_router(stories_router, prefix="/api")


# ─── Health & Readiness Probes ───────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Health"])
@app.get("/healthz", response_model=HealthResponse, tags=["Health"])
@app.get("/v1/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Liveness probe returning service operational status."""
    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        components={"service": "healthy"},
    )


@app.get("/readyz", tags=["Health"])
@app.get("/api/readyz", tags=["Health"])
@app.get("/v1/readyz", tags=["Health"])
async def readiness_check():
    """
    Readiness probe verifying PostgreSQL database connectivity.
    Returns HTTP 200 if healthy, otherwise HTTP 503.
    """
    db_healthy = False
    storage_healthy = False

    # 1. Database check
    try:
        pool = await get_db_pool()
        if pool:
            async with pool.acquire() as conn:
                val = await conn.fetchval("SELECT 1")
                if val == 1:
                    db_healthy = True
    except Exception as e:
        logger.warning(f"Readiness check DB error: {e}")

    # 2. Storage check
    try:
        if storage_service.use_s3 and storage_service.s3_client:
            storage_service.s3_client.list_buckets()
        storage_healthy = True
    except Exception as e:
        logger.warning(f"Readiness check storage error: {e}")

    all_ready = db_healthy and storage_healthy
    status_code = status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ready else "not_ready",
            "version": settings.APP_VERSION,
            "components": {
                "database": "healthy" if db_healthy else "unhealthy",
                "storage": "healthy" if storage_healthy else "unhealthy",
            },
        },
    )

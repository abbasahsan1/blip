import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from blipp_common.config import settings
from blipp_common.exceptions import (
    AppException,
    CODE_VALIDATION_ERROR,
    CODE_INTERNAL_SERVER_ERROR,
    CODE_UNAUTHORIZED,
    CODE_FORBIDDEN,
    CODE_NOT_FOUND,
    CODE_SERVICE_UNAVAILABLE,
)
from blipp_common.database import init_db_pool, close_db_pool, get_db_pool
from blipp_common.storage import storage_service
from blipp_common.events import event_bus
from app.api.v1.uploads import router as uploads_router
from app.api.v1.saves import router as saves_router
from app.models.schemas import HealthResponse
from app.event_handlers import (
    run_transcode_consumer,
    run_scheduled_publisher,
    stop_event_handlers,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("content-ingest.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting Content Ingest Service v{settings.APP_VERSION}")
    try:
        await init_db_pool()
    except Exception as e:
        logger.error(f"Database pool startup error: {e}")
    try:
        await event_bus.connect("content-ingest-service")
    except Exception as e:
        logger.error(f"Event bus startup connection error: {e}")

    # Launch transcode event consumer & scheduled post publisher background workers
    consumer_task = asyncio.create_task(run_transcode_consumer())
    publisher_task = asyncio.create_task(run_scheduled_publisher())

    yield

    stop_event_handlers()
    consumer_task.cancel()
    publisher_task.cancel()
    await asyncio.gather(consumer_task, publisher_task, return_exceptions=True)

    try:
        await event_bus.close()
    except Exception as e:
        logger.error(f"Event bus shutdown error: {e}")
    try:
        await close_db_pool()
    except Exception as e:
        logger.error(f"Database pool shutdown error: {e}")
    logger.info("Shutting down Content Ingest Service")


app = FastAPI(
    title="Blipp Content Ingest Service",
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
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

# CORS configuration: permissive during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Standard Error Envelope Handlers ────────────────────────────────────────

def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    req_id = get_request_id(request)
    headers = exc.headers or {}
    headers["X-Request-ID"] = req_id
    return JSONResponse(
        status_code=exc.status_code,
        headers=headers,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": req_id
            }
        }
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = get_request_id(request)
    error_messages = []
    for err in exc.errors():
        loc = " -> ".join(str(item) for item in err.get("loc", []))
        error_messages.append(f"{loc}: {err.get('msg', 'invalid value')}")
    
    message = "; ".join(error_messages) if error_messages else "Request validation failed"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        headers={"X-Request-ID": req_id},
        content={
            "error": {
                "code": CODE_VALIDATION_ERROR,
                "message": message,
                "request_id": req_id
            }
        }
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    req_id = get_request_id(request)
    error_messages = []
    for err in exc.errors():
        loc = " -> ".join(str(item) for item in err.get("loc", []))
        error_messages.append(f"{loc}: {err.get('msg', 'invalid value')}")
    
    message = "; ".join(error_messages) if error_messages else "Model validation failed"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        headers={"X-Request-ID": req_id},
        content={
            "error": {
                "code": CODE_VALIDATION_ERROR,
                "message": message,
                "request_id": req_id
            }
        }
    )


@app.exception_handler(StarletteHTTPException)
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    req_id = get_request_id(request)
    
    if isinstance(exc.detail, dict):
        code = exc.detail.get("code", f"HTTP_{exc.status_code}")
        message = exc.detail.get("message", str(exc.detail))
    else:
        status_to_code = {
            400: "BAD_REQUEST",
            401: CODE_UNAUTHORIZED,
            403: CODE_FORBIDDEN,
            404: CODE_NOT_FOUND,
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            422: CODE_VALIDATION_ERROR,
            500: CODE_INTERNAL_SERVER_ERROR,
            503: CODE_SERVICE_UNAVAILABLE,
        }
        code = status_to_code.get(exc.status_code, f"HTTP_{exc.status_code}")
        message = str(exc.detail) if exc.detail else "An error occurred"

    if exc.status_code == 401:
        code = CODE_UNAUTHORIZED
        message = str(exc.detail) if exc.detail else "Invalid or expired access token"

    headers = getattr(exc, "headers", None) or {}
    headers["X-Request-ID"] = req_id
    return JSONResponse(
        status_code=exc.status_code,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": req_id
            }
        }
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    req_id = get_request_id(request)
    logger.exception(f"Unhandled exception [request_id={req_id}]: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        headers={"X-Request-ID": req_id},
        content={
            "error": {
                "code": CODE_INTERNAL_SERVER_ERROR,
                "message": "An internal server error occurred",
                "request_id": req_id
            }
        }
    )


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/docs", include_in_schema=False)
async def docs_redirect():
    return RedirectResponse(url="/api/docs")


# Mount routes under /v1/uploads and /uploads
app.include_router(uploads_router, prefix="/v1/uploads")
app.include_router(uploads_router, prefix="/uploads")
app.include_router(saves_router, prefix="/v1")
app.include_router(saves_router)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
@app.get("/healthz", response_model=HealthResponse, tags=["Health"])
@app.get("/v1/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Liveness probe."""
    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
    )


@app.get("/readyz", tags=["Health"])
@app.get("/v1/readyz", tags=["Health"])
async def readiness_check():
    """
    Readiness probe verifying PostgreSQL, MinIO S3 object storage, and NATS JetStream connectivity.
    """
    db_healthy = False
    storage_healthy = False
    event_bus_healthy = False

    # 1. Check Database
    try:
        pool = await get_db_pool()
        if pool:
            async with pool.acquire() as conn:
                val = await conn.fetchval("SELECT 1")
                if val == 1:
                    db_healthy = True
    except Exception as e:
        logger.warning(f"Readiness check DB error: {e}")

    # 2. Check MinIO / S3 Storage
    try:
        storage_healthy = await storage_service.check_health()
    except Exception as e:
        logger.warning(f"Readiness check storage error: {e}")

    # 3. Check NATS JetStream Event Bus
    try:
        event_bus_healthy = await event_bus.check_health()
    except Exception as e:
        logger.warning(f"Readiness check event bus error: {e}")

    all_ready = db_healthy and storage_healthy and event_bus_healthy
    status_code = status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ready else "not_ready",
            "version": settings.APP_VERSION,
            "components": {
                "database": "healthy" if db_healthy else "unhealthy",
                "storage": "healthy" if storage_healthy else "unhealthy",
                "event_bus": "healthy" if event_bus_healthy else "unhealthy",
            }
        }
    )

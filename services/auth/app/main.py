import logging
import uuid
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.exceptions import (
    AppException,
    CODE_VALIDATION_ERROR,
    CODE_INTERNAL_SERVER_ERROR,
    CODE_UNAUTHORIZED,
    CODE_FORBIDDEN,
    CODE_NOT_FOUND,
    CODE_SERVICE_UNAVAILABLE,
)
from app.api.v1.auth import router as auth_router
from app.api.v1.blipps import router as blipps_router
from app.api.v1.uploads import router as uploads_router
from app.api.v1.events import router as events_router
from app.api.v1.profiles import router as profiles_router
from app.api.v1.analytics import router as analytics_router
from app.core.database import init_db, close_db, get_db_pool
from app.core.storage import storage_service
from app.core.events import event_bus
from app.core.redis import close_redis
from app.models.schemas import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("auth-service.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Connected Keycloak Realm: {settings.KEYCLOAK_REALM} at {settings.KEYCLOAK_INTERNAL_URL}")
    try:
        await init_db()
    except Exception as e:
        logger.error(f"Database startup initialization note: {e}")
    try:
        await event_bus.connect()
    except Exception as e:
        logger.error(f"Event bus startup connection note: {e}")
    yield
    try:
        await event_bus.close()
    except Exception as e:
        logger.error(f"Event bus shutdown note: {e}")
    try:
        await close_db()
    except Exception as e:
        logger.error(f"Database shutdown note: {e}")
    try:
        await close_redis()
    except Exception as e:
        logger.error(f"Redis shutdown note: {e}")
    logger.info(f"Shutting down {settings.APP_NAME}")


app = FastAPI(
    title=settings.APP_NAME,
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

# CORS configuration: permit LAN requests during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3})(:\d+)?$",
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


# Mount routes under /api (legacy & SPA default) and /v1 (versioned standard)
app.include_router(auth_router, prefix="/api")
app.include_router(blipps_router, prefix="/api")
app.include_router(uploads_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(profiles_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(auth_router, prefix="/v1")
app.include_router(blipps_router, prefix="/v1")
app.include_router(uploads_router, prefix="/v1")
app.include_router(events_router, prefix="/v1")
app.include_router(profiles_router, prefix="/v1")
app.include_router(analytics_router, prefix="/v1")


@app.get("/health", response_model=HealthResponse, tags=["Health"])
@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
@app.get("/v1/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Liveness probe and readiness indicator."""
    keycloak_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.KEYCLOAK_INTERNAL_URL}/realms/{settings.KEYCLOAK_REALM}")
            keycloak_status = "healthy" if resp.status_code == 200 else f"unhealthy ({resp.status_code})"
    except Exception as e:
        keycloak_status = f"unreachable ({str(e)})"

    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        keycloak_status=keycloak_status
    )


@app.get("/readyz", tags=["Health"])
@app.get("/api/readyz", tags=["Health"])
@app.get("/v1/readyz", tags=["Health"])
async def readiness_check():
    """
    Readiness probe verifying PostgreSQL, MinIO S3 object storage, and NATS JetStream connectivity.
    Returns HTTP 200 if all components are healthy, otherwise HTTP 503.
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


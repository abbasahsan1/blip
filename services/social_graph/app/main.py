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
from app.api.v1.profiles import router as profiles_router
from app.api.v1.relationships import router as relationships_router
from app.models.profile import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("social-graph.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting Blipp Social Graph Service v{settings.APP_VERSION}")
    try:
        await init_db_pool()
        logger.info("Database connection pool initialized")
    except Exception as e:
        logger.error(f"Database pool startup error: {e}")

    try:
        await event_bus.connect(client_name="social-graph-service")
        logger.info("Connected to NATS JetStream Event Bus")
    except Exception as e:
        logger.error(f"NATS startup connection error: {e}")

    yield

    try:
        await event_bus.close()
    except Exception as e:
        logger.error(f"Event bus shutdown error: {e}")

    try:
        await close_db_pool()
    except Exception as e:
        logger.error(f"Database pool shutdown error: {e}")

    logger.info("Shutting down Blipp Social Graph Service")


app = FastAPI(
    title="Blipp Social Graph Service",
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
                "request_id": req_id,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = get_request_id(request)
    first_err = exc.errors()[0] if exc.errors() else {}
    msg = first_err.get("msg", "Invalid request parameters")
    loc = ".".join(str(l) for l in first_err.get("loc", []))
    detail_msg = f"{loc}: {msg}" if loc else msg

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        headers={"X-Request-ID": req_id},
        content={
            "error": {
                "code": CODE_VALIDATION_ERROR,
                "message": detail_msg,
                "request_id": req_id,
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    req_id = get_request_id(request)
    code = "HTTP_ERROR"
    message = str(exc.detail)

    if exc.status_code == status.HTTP_404_NOT_FOUND:
        code = CODE_NOT_FOUND
        message = "Resource not found" if exc.detail == "Not Found" else str(exc.detail)
    elif exc.status_code == status.HTTP_401_UNAUTHORIZED:
        code = CODE_UNAUTHORIZED
        message = str(exc.detail) if exc.detail else "Invalid or expired access token"
    elif exc.status_code == status.HTTP_403_FORBIDDEN:
        code = CODE_FORBIDDEN
        message = str(exc.detail) if exc.detail else "Access forbidden"

    headers = getattr(exc, "headers", None) or {}
    headers["X-Request-ID"] = req_id
    return JSONResponse(
        status_code=exc.status_code,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": req_id,
            }
        },
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
                "request_id": req_id,
            }
        },
    )


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/docs", include_in_schema=False)
async def docs_redirect():
    return RedirectResponse(url="/api/docs")


# Mount routes under /v1 (standard) and /api (compatibility)
app.include_router(profiles_router, prefix="/v1")
app.include_router(relationships_router, prefix="/v1")
app.include_router(profiles_router, prefix="/api")
app.include_router(relationships_router, prefix="/api")


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
    Readiness probe verifying PostgreSQL database and NATS JetStream connectivity.
    Returns HTTP 200 if healthy, otherwise HTTP 503.
    """
    db_healthy = False
    nats_healthy = False

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

    # 2. NATS JetStream check
    try:
        nats_healthy = await event_bus.check_health()
    except Exception as e:
        logger.warning(f"Readiness check NATS error: {e}")

    all_ready = db_healthy and nats_healthy
    status_code = status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ready else "not_ready",
            "version": settings.APP_VERSION,
            "components": {
                "database": "healthy" if db_healthy else "unhealthy",
                "nats": "healthy" if nats_healthy else "unhealthy",
            },
        },
    )

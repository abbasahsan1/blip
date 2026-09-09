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
from blipp_common.database import (
    close_db_pool,
    get_db_pool,
    init_db_pool,
    CREATE_TABLES_SQL,
)
from blipp_common.events import event_bus
from blipp_common.exceptions import (
    AppException,
    CODE_FORBIDDEN,
    CODE_INTERNAL_SERVER_ERROR,
    CODE_NOT_FOUND,
    CODE_UNAUTHORIZED,
    CODE_VALIDATION_ERROR,
)
from app.api.v1.reports import router as reports_router
from app.api.v1.moderation import router as moderation_router
from app.models.moderation import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("moderation.main")


# ─── Application Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting Blipp Moderation Service v{settings.APP_VERSION}")
    try:
        await init_db_pool()
        logger.info("Database connection pool initialized")
        # Ensure schema tables exist in blipp_moderation
        pool = await get_db_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.execute(CREATE_TABLES_SQL)
                logger.info("Ensured moderation tables and indexes exist")
    except Exception as e:
        logger.error(f"Database pool startup error: {e}")

    try:
        await event_bus.connect(client_name="moderation-service")
        logger.info("Connected to NATS JetStream Event Bus")
    except Exception as e:
        logger.warning(f"NATS startup connection warning: {e}")

    yield

    try:
        await event_bus.close()
    except Exception as e:
        logger.warning(f"Event bus shutdown note: {e}")

    try:
        await close_db_pool()
    except Exception as e:
        logger.warning(f"Database pool shutdown note: {e}")

    logger.info("Shutting down Blipp Moderation Service")


# ─── FastAPI Initialization ───────────────────────────────────────────────────

app = FastAPI(
    title="Blipp Moderation Service",
    description="Dedicated microservice for User Reports, Creator Strikes, and Content Takedowns (§3 #6, §5.5, §6.7)",
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
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = get_request_id(request)
    error_messages = []
    for err in exc.errors():
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        msg = err.get("msg", "Invalid value")
        error_messages.append(f"{loc}: {msg}")
    message = "; ".join(error_messages) if error_messages else "Request validation error"

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        headers={"X-Request-ID": req_id},
        content={
            "error": {
                "code": CODE_VALIDATION_ERROR,
                "message": message,
                "request_id": req_id,
            }
        },
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
            503: "SERVICE_UNAVAILABLE",
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


# Mount versioned routers
app.include_router(reports_router, prefix="/v1")
app.include_router(reports_router)
app.include_router(moderation_router, prefix="/v1")
app.include_router(moderation_router)


# ─── Probes ──────────────────────────────────────────────────────────────────

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
@app.get("/ready", tags=["Health"])
@app.get("/v1/ready", tags=["Health"])
async def readiness_check():
    """Readiness probe checking database and NATS event bus."""
    db_healthy = False
    event_bus_healthy = False

    try:
        pool = await get_db_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
                db_healthy = True
    except Exception as e:
        logger.warning(f"Readiness check DB error: {e}")

    try:
        event_bus_healthy = await event_bus.check_health()
    except Exception as e:
        logger.warning(f"Readiness check event bus error: {e}")

    all_ready = db_healthy and event_bus_healthy
    status_code = status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ready else "not_ready",
            "version": settings.APP_VERSION,
            "components": {
                "database": "healthy" if db_healthy else "unhealthy",
                "event_bus": "healthy" if event_bus_healthy else "unhealthy",
            },
        },
    )

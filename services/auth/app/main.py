import asyncio
import json
import logging
import uuid
import httpx
import nats
from contextlib import asynccontextmanager
from typing import Any, Dict
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
from blipp_common.events import event_bus
from blipp_common.redis import get_redis_client, close_redis
from app.api.v1.auth import router as auth_router
from app.models.schemas import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("auth-service.main")

SUSPENSION_CONSUMER_NAME = "auth-service-suspension"
_suspension_running = True


# ─── Administrative User Suspension Consumer (§6.7) ───────────────────────────

async def handle_user_suspended(data: Dict[str, Any]) -> None:
    """
    Executes administrative user suspension (§6.7):
    1. Sets user status to 'suspended' in database
    2. Revokes active refresh tokens and caches suspension flag in Redis
    """
    user_id_str = data.get("user_id")
    if not user_id_str:
        logger.warning(f"Missing user_id in user.account.suspended event: {data}")
        return

    try:
        user_uuid = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        logger.error(f"Invalid user_id in user.account.suspended: {user_id_str}")
        return

    reason = data.get("reason", "moderation_action")
    logger.warning(f"Executing administrative suspension for user {user_uuid} (reason='{reason}')")

    # 1. Update database status
    pool = await get_db_pool()
    if pool:
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE users_profile
                    SET status = 'suspended'
                    WHERE user_id = $1
                    """,
                    user_uuid,
                )
                logger.info(f"Updated users_profile status to 'suspended' for user {user_uuid}")
        except Exception as db_err:
            logger.error(f"Database error during user suspension: {db_err}")

    # 2. Revoke active refresh tokens & mark suspended in Redis
    try:
        redis_client = await get_redis_client()
        if redis_client:
            # Mark user as suspended in Redis cache (24h TTL)
            await redis_client.set(f"suspended:{user_uuid}", "1", ex=86400)

            # Scan & delete active refresh tokens / session keys
            patterns = [
                f"refresh:{user_uuid}*",
                f"session:{user_uuid}*",
                f"token:{user_uuid}*",
                f"auth:{user_uuid}*",
            ]
            for pat in patterns:
                keys = await redis_client.keys(pat)
                if keys:
                    await redis_client.delete(*keys)
                    logger.info(f"Revoked {len(keys)} active Redis token/session key(s) for user {user_uuid}")
    except Exception as redis_err:
        logger.error(f"Redis error during user suspension revocation: {redis_err}")


async def run_suspension_consumer() -> None:
    """
    Subscribes to user.account.suspended events on NATS JetStream (ENGAGEMENT stream)
    using durable consumer 'auth-service-suspension'.
    """
    global _suspension_running
    while _suspension_running:
        if not event_bus.is_connected or not event_bus.js:
            connected = await event_bus.connect("auth-service-suspension-consumer")
            if not connected:
                await asyncio.sleep(2.0)
                continue

        js = event_bus.js
        try:
            psub = await js.pull_subscribe(
                subject="user.account.suspended",
                durable=SUSPENSION_CONSUMER_NAME,
                stream=settings.NATS_STREAM_ENGAGEMENT,
            )
            logger.info(f"Durable pull consumer '{SUSPENSION_CONSUMER_NAME}' subscribed to 'user.account.suspended'")

            while _suspension_running:
                try:
                    msgs = await psub.fetch(batch=5, timeout=2.0)
                    for msg in msgs:
                        try:
                            payload = json.loads(msg.data.decode("utf-8"))
                            await handle_user_suspended(payload)
                            await msg.ack()
                        except Exception as msg_err:
                            logger.exception(f"Error handling user.account.suspended: {msg_err}")
                            await msg.ack()
                except (nats.errors.TimeoutError, asyncio.TimeoutError):
                    continue
                except asyncio.CancelledError:
                    _suspension_running = False
                    break
                except Exception as loop_err:
                    if _suspension_running:
                        logger.warning(f"Error in suspension fetch loop: {loop_err}")
                        await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            break
        except Exception as conn_err:
            if _suspension_running:
                logger.warning(f"NATS subscription error in suspension consumer: {conn_err}. Reconnecting in 3s...")
                await asyncio.sleep(3.0)

    logger.info("Suspension consumer background task stopped.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _suspension_running
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Connected Keycloak Realm: {settings.KEYCLOAK_REALM} at {settings.KEYCLOAK_INTERNAL_URL}")
    try:
        await init_db_pool()
    except Exception as e:
        logger.error(f"Database startup initialization note: {e}")

    try:
        await event_bus.connect("auth-service")
    except Exception as e:
        logger.warning(f"Event bus startup error: {e}")

    # Launch user account suspension background consumer (§6.7)
    _suspension_running = True
    suspension_task = asyncio.create_task(run_suspension_consumer())

    yield

    _suspension_running = False
    suspension_task.cancel()
    await asyncio.gather(suspension_task, return_exceptions=True)

    try:
        await event_bus.close()
    except Exception as e:
        logger.warning(f"Event bus shutdown note: {e}")

    try:
        await close_redis()
    except Exception as e:
        logger.warning(f"Redis shutdown note: {e}")

    try:
        await close_db_pool()
    except Exception as e:
        logger.error(f"Database shutdown note: {e}")
    logger.info(f"Shutting down {settings.APP_NAME}")


app = FastAPI(
    title="Blipp Auth Service",
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

# CORS configuration: permit LAN and web requests during development
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


# Mount routes under /api (legacy & SPA default) and /v1 (versioned standard)
app.include_router(auth_router, prefix="/api")
app.include_router(auth_router, prefix="/v1")


@app.get("/healthz", tags=["Health"])
@app.get("/api/healthz", tags=["Health"])
@app.get("/v1/healthz", tags=["Health"])
def healthz():
    """Liveness probe returning immediate healthy status."""
    return {"status": "ok"}


@app.get("/health", response_model=HealthResponse, tags=["Health"])
@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
@app.get("/v1/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Detailed health check indicator."""
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
    Readiness probe verifying PostgreSQL and Keycloak connectivity.
    Returns HTTP 200 if database is healthy.
    """
    db_healthy = False
    keycloak_healthy = False

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

    # 2. Check Keycloak (non-blocking for readiness)
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.KEYCLOAK_INTERNAL_URL}/realms/{settings.KEYCLOAK_REALM}")
            if resp.status_code == 200:
                keycloak_healthy = True
    except Exception as e:
        logger.warning(f"Readiness check Keycloak error: {e}")

    all_ready = db_healthy
    status_code = status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ready else "not_ready",
            "version": settings.APP_VERSION,
            "components": {
                "database": "healthy" if db_healthy else "unhealthy",
                "keycloak": "healthy" if keycloak_healthy else "unhealthy",
            }
        }
    )

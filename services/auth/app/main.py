import logging
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.auth import router as auth_router
from app.api.v1.protected import router as protected_router
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
    yield
    logger.info(f"Shutting down {settings.APP_NAME}")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

@app.get("/docs", include_in_schema=False)
async def docs_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/api/docs")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production ingress handles edge security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers under /api
app.include_router(auth_router, prefix="/api")
app.include_router(protected_router, prefix="/api")


@app.get("/health", response_model=HealthResponse, tags=["Health"])
@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Liveness probe and readiness indicator."""
    keycloak_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.KEYCLOAK_INTERNAL_URL}/health/ready")
            keycloak_status = "healthy" if resp.status_code == 200 else f"unhealthy ({resp.status_code})"
    except Exception as e:
        keycloak_status = f"unreachable ({str(e)})"

    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        keycloak_status=keycloak_status
    )

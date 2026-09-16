import time
import uuid
import logging
from typing import Dict, Any, Optional, List
import httpx
from fastapi import Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from pydantic import BaseModel, Field

from blipp_common.config import settings
from blipp_common.exceptions import AppException
from blipp_common.redis import get_redis_client

logger = logging.getLogger("blipp_common.security")


class AuthenticatedUser(BaseModel):
    user_id: uuid.UUID = Field(..., description="Subject claim (sub) extracted as UUID")
    id: str = Field(..., description="String representation of user_id for compatibility")
    username: str = Field(default="", description="Keycloak username")
    email: Optional[str] = Field(default=None, description="User email")
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    roles: List[str] = Field(default_factory=list, description="Assigned realm roles")


# Compatibility alias
TokenData = AuthenticatedUser
UserResponse = AuthenticatedUser

# Set auto_error=False so we intercept missing or malformed headers directly
# and return the exact required error envelope (401 UNAUTHORIZED)
security_scheme = HTTPBearer(auto_error=False)

# In-memory cache for Keycloak JWKS
_jwks_cache: Dict[str, Any] = {}
_jwks_cached_at: float = 0
JWKS_CACHE_TTL_SECONDS = 600  # 10 minutes


async def get_jwks(force_refresh: bool = False) -> Dict[str, Any]:
    global _jwks_cache, _jwks_cached_at
    current_time = time.time()

    if not force_refresh and _jwks_cache and (current_time - _jwks_cached_at < JWKS_CACHE_TTL_SECONDS):
        return _jwks_cache

    primary_url = settings.get_jwks_url()
    candidate_urls = [
        primary_url,
        f"{settings.KEYCLOAK_INTERNAL_URL}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/certs",
        f"http://keycloak.blipp.svc.cluster.local:8080/keycloak/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/certs",
        f"http://keycloak.blipp.svc.cluster.local:8080/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/certs",
    ]
    seen = set()
    urls_to_try = [u for u in candidate_urls if not (u in seen or seen.add(u))]

    for jwks_url in urls_to_try:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(jwks_url)
                if resp.status_code == 200:
                    _jwks_cache = resp.json()
                    _jwks_cached_at = current_time
                    logger.info(f"Successfully cached Keycloak JWKS from {jwks_url}")
                    return _jwks_cache
        except Exception as e:
            logger.debug(f"Could not reach JWKS at {jwks_url}: {e}")

    if _jwks_cache:
        logger.warning("Using stale in-memory JWKS cache as fallback")
        return _jwks_cache

    logger.error("Keycloak JWKS endpoint unreachable")
    raise AppException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="UNAUTHORIZED",
        message="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"}
    )


async def verify_token(token: str) -> Dict[str, Any]:
    """Validate RSA signature and issuer locally against Keycloak JWKS."""
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    kid = unverified_header.get("kid")
    if not kid:
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    jwks = await get_jwks()
    keys = jwks.get("keys", [])
    key_dict = next((k for k in keys if k.get("kid") == kid), None)

    if not key_dict:
        # Refresh cache once in case the signing key was rotated
        jwks = await get_jwks(force_refresh=True)
        keys = jwks.get("keys", [])
        key_dict = next((k for k in keys if k.get("kid") == kid), None)

    if not key_dict:
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        payload = jwt.decode(
            token,
            key_dict,
            algorithms=["RS256"],
            options={
                "verify_aud": False,  # Allow tokens issued across realm clients
                "verify_exp": True,
            }
        )

        token_issuer = payload.get("iss", "")
        expected_realm_suffix = f"/realms/{settings.KEYCLOAK_REALM}"
        if not token_issuer.endswith(expected_realm_suffix):
            logger.warning(f"Token issuer mismatch: {token_issuer}")
            raise AppException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="UNAUTHORIZED",
                message="Invalid or expired access token",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Redis blocklist check
        jti = payload.get("jti")
        sub = payload.get("sub")
        if jti or sub:
            try:
                redis_client = await get_redis_client()
                if jti and await redis_client.get(f"blocklist:jti:{jti}"):
                    raise AppException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        code="UNAUTHORIZED",
                        message="Token has been revoked",
                        headers={"WWW-Authenticate": "Bearer"}
                    )
                if sub and await redis_client.get(f"blocklist:sub:{sub}"):
                    raise AppException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        code="UNAUTHORIZED",
                        message="Account is suspended or blocked",
                        headers={"WWW-Authenticate": "Bearer"}
                    )
            except AppException:
                raise
            except Exception as e:
                logger.warning(f"Redis blocklist check failed: {e}")

        return payload
    except (jwt.ExpiredSignatureError, JWTError):
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme)
) -> AuthenticatedUser:
    """
    FastAPI dependency that:
    1. Reads Authorization: Bearer <token> header.
    2. Validates JWT signature locally using cached JWKS.
    3. Extracts subject claim (sub) as UUID user_id.
    4. Rejects invalid or expired credentials with strict UNAUTHORIZED envelope.
    """
    if not credentials or not credentials.credentials:
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    payload = await verify_token(credentials.credentials)

    sub = payload.get("sub")
    if not sub:
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        user_uuid = uuid.UUID(str(sub))
    except (ValueError, TypeError):
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    realm_access = payload.get("realm_access", {})
    roles = realm_access.get("roles", [])

    return AuthenticatedUser(
        user_id=user_uuid,
        id=str(user_uuid),
        username=payload.get("preferred_username", str(user_uuid)),
        email=payload.get("email"),
        first_name=payload.get("given_name"),
        last_name=payload.get("family_name"),
        roles=roles
    )


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme)
) -> Optional[AuthenticatedUser]:
    """
    Returns AuthenticatedUser if valid Bearer token is provided; otherwise returns None.
    Does not raise 401 on missing credentials, allowing guest access to public feeds.
    """
    if not credentials or not credentials.credentials:
        return None
    try:
        return await get_current_user(credentials)
    except Exception:
        return None


__all__ = [
    "AuthenticatedUser",
    "TokenData",
    "UserResponse",
    "security_scheme",
    "get_jwks",
    "verify_token",
    "get_current_user",
    "get_optional_current_user",
]

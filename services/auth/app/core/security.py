import time
import logging
from typing import Dict, Any
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

from app.core.config import settings
from app.models.schemas import UserResponse

logger = logging.getLogger("auth-service.security")

security_scheme = HTTPBearer(auto_error=True)

# In-memory cache for Keycloak JWKS
_jwks_cache: Dict[str, Any] = {}
_jwks_cached_at: float = 0
JWKS_CACHE_TTL_SECONDS = 600  # 10 minutes


async def get_jwks(force_refresh: bool = False) -> Dict[str, Any]:
    global _jwks_cache, _jwks_cached_at
    current_time = time.time()
    
    if not force_refresh and _jwks_cache and (current_time - _jwks_cached_at < JWKS_CACHE_TTL_SECONDS):
        return _jwks_cache

    # Keycloak 26 exposes JWKS under /realms/<realm>/protocol/openid-connect/certs
    # Try internal cluster service URL
    candidate_urls = [
        f"{settings.KEYCLOAK_INTERNAL_URL}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/certs",
        f"http://keycloak.blipp.svc.cluster.local:8080/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/certs",
        f"http://keycloak.blipp.svc.cluster.local:8080/keycloak/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/certs",
    ]

    for jwks_url in candidate_urls:
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(jwks_url)
                if resp.status_code == 200:
                    _jwks_cache = resp.json()
                    _jwks_cached_at = current_time
                    logger.info(f"Successfully fetched and cached Keycloak JWKS from {jwks_url}")
                    return _jwks_cache
        except Exception as e:
            logger.debug(f"Could not reach JWKS at {jwks_url}: {e}")

    if _jwks_cache:
        logger.warning("Using stale JWKS cache as fallback")
        return _jwks_cache

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Keycloak Identity Provider JWKS certs endpoint is unreachable"
    )


async def verify_token(token: str) -> Dict[str, Any]:
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token header: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )

    kid = unverified_header.get("kid")
    if not kid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token header missing 'kid'",
            headers={"WWW-Authenticate": "Bearer"}
        )

    jwks = await get_jwks()
    keys = jwks.get("keys", [])
    key_dict = next((k for k in keys if k.get("kid") == kid), None)

    if not key_dict:
        # Refresh cache once in case key was rotated
        jwks = await get_jwks(force_refresh=True)
        keys = jwks.get("keys", [])
        key_dict = next((k for k in keys if k.get("kid") == kid), None)

    if not key_dict:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Public key matching token kid not found in Keycloak JWKS",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        # Verify RSA signature and expiration
        payload = jwt.decode(
            token,
            key_dict,
            algorithms=["RS256"],
            options={
                "verify_aud": False,  # Allow tokens issued to realm clients
                "verify_exp": True,
            }
        )
        
        # Verify that the token was issued for the blipp realm
        token_issuer = payload.get("iss", "")
        expected_realm_suffix = f"/realms/{settings.KEYCLOAK_REALM}"
        
        if not token_issuer.endswith(expected_realm_suffix):
            logger.warning(
                f"Token issuer mismatch: got '{token_issuer}', expected realm suffix '{expected_realm_suffix}'"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token issuer: {token_issuer}",
                headers={"WWW-Authenticate": "Bearer"}
            )
            
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please refresh your session.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme)
) -> UserResponse:
    token = credentials.credentials
    payload = await verify_token(token)
    
    realm_access = payload.get("realm_access", {})
    roles = realm_access.get("roles", [])
    
    return UserResponse(
        id=payload.get("sub", ""),
        username=payload.get("preferred_username", payload.get("sub", "")),
        email=payload.get("email"),
        first_name=payload.get("given_name"),
        last_name=payload.get("family_name"),
        roles=roles
    )


async def get_admin_token() -> str:
    """Fetch Keycloak Admin Token for user management."""
    token_urls = [
        f"{settings.KEYCLOAK_INTERNAL_URL}/realms/master/protocol/openid-connect/token",
        f"http://keycloak.blipp.svc.cluster.local:8080/realms/master/protocol/openid-connect/token",
        f"http://keycloak.blipp.svc.cluster.local:8080/keycloak/realms/master/protocol/openid-connect/token",
    ]
    payload = {
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": settings.KEYCLOAK_ADMIN,
        "password": settings.KEYCLOAK_ADMIN_PASSWORD,
    }
    
    async with httpx.AsyncClient(timeout=8.0) as client:
        for url in token_urls:
            try:
                resp = await client.post(url, data=payload)
                if resp.status_code == 200:
                    return resp.json()["access_token"]
            except Exception as e:
                logger.debug(f"Failed admin auth against {url}: {e}")

    logger.error("Failed to obtain Keycloak admin token from all candidate endpoints")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to authenticate with Keycloak administrative interface"
    )

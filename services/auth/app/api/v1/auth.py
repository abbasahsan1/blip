import logging
from typing import List
import httpx
from fastapi import APIRouter, Depends, status

from app.core.config import settings
from app.core.exceptions import (
    AppException,
    CODE_INVALID_CREDENTIALS,
    CODE_SERVICE_UNAVAILABLE,
    CODE_USER_ALREADY_EXISTS,
    CODE_REGISTRATION_FAILED,
    CODE_INVALID_TOKEN,
)
from app.core.security import get_current_user, get_admin_token, verify_token
from app.models.schemas import (
    LoginRequest,
    RegisterRequest,
    RefreshRequest,
    LogoutRequest,
    TokenResponse,
    UserResponse,
    MessageResponse,
)

logger = logging.getLogger("auth-service.api.auth")
router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_candidate_keycloak_urls(path: str) -> List[str]:
    clean_path = path.lstrip("/")
    return [
        f"{settings.KEYCLOAK_INTERNAL_URL}/{clean_path}",
        f"http://keycloak.blipp.svc.cluster.local:8080/{clean_path}",
        f"http://keycloak.blipp.svc.cluster.local:8080/keycloak/{clean_path}",
    ]


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """Authenticate user with Keycloak via Direct Access Grants (Password grant)."""
    token_path = f"realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/token"
    token_urls = get_candidate_keycloak_urls(token_path)
    
    login_id = req.identifier
    data = {
        "grant_type": "password",
        "client_id": settings.KEYCLOAK_CLIENT_ID,
        "username": login_id,
        "password": req.password,
        "scope": "openid profile email",
    }
    if settings.KEYCLOAK_CLIENT_SECRET:
        data["client_secret"] = settings.KEYCLOAK_CLIENT_SECRET

    resp = None
    last_error = None

    async with httpx.AsyncClient(timeout=8.0) as client:
        for url in token_urls:
            try:
                candidate_resp = await client.post(url, data=data)
                if candidate_resp.status_code != 404:
                    resp = candidate_resp
                    break
            except Exception as e:
                last_error = e

    if resp is None:
        logger.error(f"Failed to reach Keycloak token endpoint: {last_error}")
        raise AppException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=CODE_SERVICE_UNAVAILABLE,
            message="Authentication provider unreachable"
        )

    if resp.status_code != 200:
        logger.warning(f"Keycloak authentication failed for user identifier '{login_id}': {resp.text}")
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=CODE_INVALID_CREDENTIALS,
            message="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = resp.json()
    access_token = token_data["access_token"]
    
    # Extract user profile from verified token claims
    payload = await verify_token(access_token)
    user = UserResponse(
        id=payload.get("sub", ""),
        username=payload.get("preferred_username", login_id),
        email=payload.get("email"),
        first_name=payload.get("given_name"),
        last_name=payload.get("family_name"),
        roles=payload.get("realm_access", {}).get("roles", [])
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=token_data.get("refresh_token", ""),
        token_type=token_data.get("token_type", "Bearer"),
        expires_in=token_data.get("expires_in", 300),
        refresh_expires_in=token_data.get("refresh_expires_in"),
        user=user
    )


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest):
    """Register a new user in Keycloak using Keycloak Admin API."""
    admin_token = await get_admin_token()
    users_path = f"admin/realms/{settings.KEYCLOAK_REALM}/users"
    users_urls = get_candidate_keycloak_urls(users_path)

    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }

    user_payload = {
        "username": req.username,
        "email": req.email,
        "enabled": True,
        "firstName": req.first_name,
        "lastName": req.last_name,
        "credentials": [
            {
                "type": "password",
                "value": req.password,
                "temporary": False
            }
        ]
    }

    resp = None
    async with httpx.AsyncClient(timeout=8.0) as client:
        for url in users_urls:
            try:
                candidate_resp = await client.post(url, headers=headers, json=user_payload)
                if candidate_resp.status_code != 404:
                    resp = candidate_resp
                    break
            except Exception as e:
                logger.debug(f"User registration candidate {url} failed: {e}")

    if resp is None:
        raise AppException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=CODE_SERVICE_UNAVAILABLE,
            message="Keycloak user registration interface unreachable"
        )

    if resp.status_code == 201:
        return MessageResponse(message="User registered successfully", success=True)
    elif resp.status_code == 409:
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            code=CODE_USER_ALREADY_EXISTS,
            message="Username or email is already registered"
        )
    else:
        logger.error(f"Failed to create user in Keycloak: {resp.status_code} - {resp.text}")
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=CODE_REGISTRATION_FAILED,
            message=f"Registration failed: {resp.text}"
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest):
    """Refresh an expired access token using a valid refresh token."""
    token_path = f"realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/token"
    token_urls = get_candidate_keycloak_urls(token_path)
    
    data = {
        "grant_type": "refresh_token",
        "client_id": settings.KEYCLOAK_CLIENT_ID,
        "refresh_token": req.refresh_token,
    }
    if settings.KEYCLOAK_CLIENT_SECRET:
        data["client_secret"] = settings.KEYCLOAK_CLIENT_SECRET

    resp = None
    async with httpx.AsyncClient(timeout=8.0) as client:
        for url in token_urls:
            try:
                candidate_resp = await client.post(url, data=data)
                if candidate_resp.status_code != 404:
                    resp = candidate_resp
                    break
            except Exception:
                pass

    if resp is None or resp.status_code != 200:
        raise AppException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=CODE_INVALID_TOKEN,
            message="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = resp.json()
    access_token = token_data["access_token"]
    payload = await verify_token(access_token)
    
    user = UserResponse(
        id=payload.get("sub", ""),
        username=payload.get("preferred_username", ""),
        email=payload.get("email"),
        first_name=payload.get("given_name"),
        last_name=payload.get("family_name"),
        roles=payload.get("realm_access", {}).get("roles", [])
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=token_data.get("refresh_token", ""),
        token_type=token_data.get("token_type", "Bearer"),
        expires_in=token_data.get("expires_in", 300),
        refresh_expires_in=token_data.get("refresh_expires_in"),
        user=user
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(req: LogoutRequest):
    """Invalidate active session in Keycloak."""
    logout_path = f"realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/logout"
    logout_urls = get_candidate_keycloak_urls(logout_path)
    
    data = {
        "client_id": settings.KEYCLOAK_CLIENT_ID,
        "refresh_token": req.refresh_token,
    }
    if settings.KEYCLOAK_CLIENT_SECRET:
        data["client_secret"] = settings.KEYCLOAK_CLIENT_SECRET

    async with httpx.AsyncClient(timeout=8.0) as client:
        for url in logout_urls:
            try:
                resp = await client.post(url, data=data)
                if resp.status_code in (200, 204):
                    break
            except Exception:
                pass

    return MessageResponse(message="Successfully logged out", success=True)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: UserResponse = Depends(get_current_user)):
    """Retrieve authenticated user's profile and active roles."""
    return current_user

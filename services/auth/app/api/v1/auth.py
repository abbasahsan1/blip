import logging
from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.schemas import AuthenticatedUser

logger = logging.getLogger("auth-service.api.auth")
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/me", response_model=AuthenticatedUser)
async def get_me(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Retrieve and verify authenticated user profile via JWT."""
    return current_user


@router.get("/verify", response_model=AuthenticatedUser)
async def verify_session(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Lightweight session verification endpoint."""
    return current_user

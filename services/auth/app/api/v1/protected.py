import time
from fastapi import APIRouter, Depends
from app.core.security import get_current_user
from app.models.schemas import AuthenticatedUser

router = APIRouter(prefix="/protected", tags=["Protected Resources"])


@router.get("/data")
async def get_protected_data(current_user: AuthenticatedUser = Depends(get_current_user)):
    """A sample protected endpoint that requires a valid Keycloak JWT session."""
    return {
        "status": "success",
        "message": f"Hello, {current_user.username}! You have successfully accessed a secured FastAPI endpoint.",
        "timestamp": time.time(),
        "user_id": str(current_user.user_id),
        "roles": current_user.roles,
        "service": "Blipp Auth Microservice",
        "cluster_context": "Internal k3d production cluster"
    }

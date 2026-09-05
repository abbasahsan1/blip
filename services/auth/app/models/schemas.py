import uuid
from typing import List, Optional
from pydantic import BaseModel, Field


class AuthenticatedUser(BaseModel):
    user_id: uuid.UUID = Field(..., description="Subject claim (sub) extracted as UUID")
    id: str = Field(..., description="String representation of user_id for compatibility")
    username: str = Field(default="", description="Keycloak username")
    email: Optional[str] = Field(default=None, description="User email")
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    roles: List[str] = Field(default_factory=list, description="Assigned realm roles")


# Compatibility alias
UserResponse = AuthenticatedUser


class MessageResponse(BaseModel):
    message: str
    success: bool = True


class HealthResponse(BaseModel):
    status: str
    version: str
    keycloak_status: str

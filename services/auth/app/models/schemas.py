import uuid
from typing import List, Optional
from pydantic import BaseModel, Field

from blipp_common.security import AuthenticatedUser, TokenData, UserResponse


class MessageResponse(BaseModel):
    message: str
    success: bool = True


class HealthResponse(BaseModel):
    status: str
    version: str
    keycloak_status: str


__all__ = [
    "AuthenticatedUser",
    "TokenData",
    "UserResponse",
    "MessageResponse",
    "HealthResponse",
]

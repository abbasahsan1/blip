from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field, model_validator


class LoginRequest(BaseModel):
    username: Optional[str] = Field(default=None, description="Username")
    email: Optional[str] = Field(default=None, description="Email")
    password: str = Field(..., description="User password", min_length=1)

    @model_validator(mode="after")
    def check_identifier(self):
        if not self.username and not self.email:
            raise ValueError("Either 'username' or 'email' must be provided")
        return self

    @property
    def identifier(self) -> str:
        return self.username or self.email or ""


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)
    first_name: Optional[str] = Field(default="", max_length=50)
    last_name: Optional[str] = Field(default="", max_length=50)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_expires_in: Optional[int] = None
    user: Optional["UserResponse"] = None


class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    roles: List[str] = []


class MessageResponse(BaseModel):
    message: str
    success: bool = True


class HealthResponse(BaseModel):
    status: str
    version: str
    keycloak_status: str

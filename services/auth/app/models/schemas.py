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


class BlippResponse(BaseModel):
    blipp_id: uuid.UUID
    creator_id: uuid.UUID
    title: str
    audio_url: str
    audio_variants: dict = Field(default_factory=dict)
    duration_seconds: int = 0
    status: str = "published"
    created_at: Optional[str] = None


class FeedItemResponse(BaseModel):
    blipp_id: uuid.UUID
    creator_id: uuid.UUID
    title: str
    audio_url: str
    audio_variants: dict = Field(default_factory=dict)
    duration_seconds: int = 0


class FeedResponse(BaseModel):
    items: List[FeedItemResponse] = Field(default_factory=list)
    next_cursor: Optional[str] = None


class UploadPresignRequest(BaseModel):
    file_name: str
    mime_type: Optional[str] = "audio/mpeg"
    size_bytes: int


class UploadPresignResponse(BaseModel):
    upload_id: str
    storage_key: str
    presigned_url: str
    content_type: str


class UploadCompleteRequest(BaseModel):
    title: str
    description: Optional[str] = None
    duration_seconds: int = 0


class TelemetryEvent(BaseModel):
    event_type: str = "play_progress"
    user_id: str
    blipp_id: str
    session_id: str
    position_seconds: int
    duration_seconds: int
    device_signal: str
    timestamp: str


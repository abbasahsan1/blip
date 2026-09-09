import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

from blipp_common.security import AuthenticatedUser, TokenData


class HealthResponse(BaseModel):
    status: str
    version: str


class UploadResponse(BaseModel):
    upload_id: uuid.UUID
    status: str = "queued"
    message: str = "Upload received and queued for processing"


class UploadStatusResponse(BaseModel):
    upload_id: uuid.UUID
    creator_id: uuid.UUID
    raw_file_url: str
    upload_type: str = "audio"
    processing_status: str = "queued"
    title: Optional[str] = None
    description: Optional[str] = None
    created_at: Optional[str] = None


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
    scheduled_at: Optional[datetime] = None



class BlippResponse(BaseModel):
    blipp_id: uuid.UUID
    creator_id: uuid.UUID
    title: Optional[str] = None
    description: Optional[str] = None
    audio_url: str
    audio_variants: dict = Field(default_factory=dict)
    duration_seconds: float = 0.0
    language: str = "en"
    status: str = "published"
    scheduled_at: Optional[str] = None
    source_type: str = "direct_upload"
    parent_upload_id: Optional[uuid.UUID] = None
    created_at: Optional[str] = None


__all__ = [
    "AuthenticatedUser",
    "TokenData",
    "HealthResponse",
    "UploadResponse",
    "UploadStatusResponse",
    "UploadPresignRequest",
    "UploadPresignResponse",
    "UploadCompleteRequest",
    "BlippResponse",
]

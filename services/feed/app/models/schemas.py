import uuid
from typing import List, Optional
from pydantic import BaseModel, Field

from blipp_common.security import AuthenticatedUser, TokenData


class HealthResponse(BaseModel):
    status: str
    version: str


class FeedItemResponse(BaseModel):
    blipp_id: uuid.UUID
    creator_id: uuid.UUID
    title: Optional[str] = None
    description: Optional[str] = None
    audio_url: str
    audio_variants: dict = Field(default_factory=dict)
    duration_seconds: float = 0.0
    author: Optional[str] = None
    username: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


class FeedResponse(BaseModel):
    items: List[FeedItemResponse] = Field(default_factory=list)
    next_cursor: Optional[str] = None


__all__ = [
    "HealthResponse",
    "FeedItemResponse",
    "FeedResponse",
    "AuthenticatedUser",
    "TokenData",
]

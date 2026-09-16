import uuid
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from blipp_common.security import AuthenticatedUser, TokenData


class HealthResponse(BaseModel):
    status: str
    version: str


class FeedItemResponse(BaseModel):
    item_type: str = "blipp"
    id: Optional[str] = None
    blipp_id: Union[uuid.UUID, str]
    creator_id: Optional[Union[uuid.UUID, str]] = None
    provider: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    audio_url: str
    audio_variants: dict = Field(default_factory=dict)
    duration_seconds: float = 0.0
    author: Optional[str] = None
    username: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    creator: Optional[Dict[str, Any]] = None
    likes_count: int = 0
    is_liked: bool = False
    is_saved: bool = False
    is_following: bool = False


class FeedResponse(BaseModel):
    items: List[FeedItemResponse] = Field(default_factory=list)
    next_cursor: Optional[str] = None
    has_more: bool = True


class BatchFeedItemsRequest(BaseModel):
    blipp_ids: List[Union[uuid.UUID, str]]


class BatchFeedItemsResponse(BaseModel):
    items: List[FeedItemResponse] = Field(default_factory=list)


__all__ = [
    "HealthResponse",
    "FeedItemResponse",
    "FeedResponse",
    "BatchFeedItemsRequest",
    "BatchFeedItemsResponse",
    "AuthenticatedUser",
    "TokenData",
]


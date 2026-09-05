import uuid
from typing import Optional
from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    display_name: str
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: Optional[str] = None


class UserProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=255)
    bio: Optional[str] = None
    avatar_url: Optional[str] = None

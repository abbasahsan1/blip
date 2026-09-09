import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from blipp_common.database import Base

# ─── Regular Expressions ───────────────────────────────────────────────────────
USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_]{3,30}$")


# ─── SQLAlchemy Relational Models (§5.2) ───────────────────────────────────────

class UserProfile(Base):
    """
    SQLAlchemy model representing a user's public profile within the Social Graph.
    """
    __tablename__ = "users_profile"

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=True)
    bio = Column(Text, nullable=True)
    avatar_url = Column(Text, nullable=True)
    is_creator = Column(Boolean, default=False, nullable=False)
    verification_status = Column(String(50), default="unverified", nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Follow(Base):
    """
    Relational edge representing a directed follow relationship (§5.2):
    follower_id follows followee_id.
    """
    __tablename__ = "follows"

    follower_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users_profile.user_id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
        nullable=False,
    )
    followee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users_profile.user_id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("follower_id", "followee_id", name="uq_follower_followee"),
    )


# ─── Pydantic Validation & Transfer Schemas ────────────────────────────────────

class ProfileCreate(BaseModel):
    """Payload for claiming a unique username on first login (§6.1)."""
    username: str = Field(..., min_length=3, max_length=30, description="Unique handle (3-30 chars, alphanumeric + underscores)")
    display_name: Optional[str] = Field(None, max_length=255)
    bio: Optional[str] = Field(None, max_length=1000)
    avatar_url: Optional[str] = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not USERNAME_REGEX.match(cleaned):
            raise ValueError(
                "Username must be 3-30 characters long and contain only letters, numbers, and underscores"
            )
        return cleaned


class ProfileUpdate(BaseModel):
    """Payload for updating mutable profile fields."""
    display_name: Optional[str] = Field(None, max_length=255)
    bio: Optional[str] = Field(None, max_length=1000)
    avatar_url: Optional[str] = None


class ProfileResponse(BaseModel):
    """Standard user profile representation with computed social counts and relationship status."""
    user_id: uuid.UUID
    username: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    is_creator: bool = False
    verification_status: str = "unverified"
    created_at: Optional[str] = None
    followers_count: int = 0
    following_count: int = 0
    is_following: bool = False


class FollowActionResponse(BaseModel):
    """Result of a follow or unfollow operation."""
    success: bool = True
    follower_id: uuid.UUID
    followee_id: uuid.UUID
    is_following: bool


class FollowerItem(BaseModel):
    """A user in a follower/following list."""
    user_id: uuid.UUID
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    is_creator: bool = False
    verification_status: str = "unverified"
    followed_at: Optional[str] = None
    is_following: bool = False


class FollowListResponse(BaseModel):
    """Paginated list of followers or followed users."""
    items: List[FollowerItem]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    """Service health status."""
    status: str
    version: str
    components: dict

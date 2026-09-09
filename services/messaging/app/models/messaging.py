import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from blipp_common.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def default_story_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=24)


# ─── SQLAlchemy Declarative Models (§5.4) ───────────────────────────────────────

class DMThread(Base):
    """
    Direct Messaging thread entity representing a conversation between 2 participants.
    """
    __tablename__ = "dm_threads"

    thread_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    participant_ids = Column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    messages = relationship(
        "DMMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="DMMessage.created_at.desc()",
    )

    __table_args__ = (
        Index("idx_dm_threads_participants", participant_ids, postgresql_using="gin"),
    )


class DMMessage(Base):
    """
    Message item inside a DM thread (§5.4).
    Supports plain text messages or Blipp rich content shares.
    """
    __tablename__ = "dm_messages"

    message_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    thread_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dm_threads.thread_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    message_type = Column(
        String(50),
        default="text",
        nullable=False,
    )  # 'text' | 'blipp_share'
    blipp_id = Column(
        UUID(as_uuid=True),
        nullable=True,
    )
    body = Column(
        Text,
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )

    thread = relationship("DMThread", back_populates="messages")


class Story(Base):
    """
    24-Hour Ephemeral Audio Story (§5.4).
    Expires automatically 24 hours after creation.
    """
    __tablename__ = "stories"

    story_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    creator_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    audio_url = Column(
        String(1024),
        nullable=False,
    )
    duration_seconds = Column(
        Float,
        default=0.0,
        nullable=False,
    )
    expires_at = Column(
        DateTime(timezone=True),
        default=default_story_expiry,
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )


# ─── Pydantic Transfer Schemas ──────────────────────────────────────────────────

class ThreadCreateRequest(BaseModel):
    recipient_id: uuid.UUID = Field(..., description="Target participant user ID to start or open a thread with")


class MessageCreateRequest(BaseModel):
    message_type: str = Field(default="text", description="'text' or 'blipp_share'")
    body: Optional[str] = Field(default=None, max_length=5000, description="Message text content")
    blipp_id: Optional[uuid.UUID] = Field(default=None, description="Referenced Blipp ID when message_type is 'blipp_share'")

    @field_validator("message_type")
    @classmethod
    def validate_message_type(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ("text", "blipp_share"):
            raise ValueError("message_type must be either 'text' or 'blipp_share'")
        return clean


class DMMessageResponse(BaseModel):
    message_id: uuid.UUID
    thread_id: uuid.UUID
    sender_id: uuid.UUID
    message_type: str
    blipp_id: Optional[uuid.UUID] = None
    body: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DMThreadResponse(BaseModel):
    thread_id: uuid.UUID
    participant_ids: List[uuid.UUID]
    created_at: datetime
    updated_at: Optional[datetime] = None
    latest_message: Optional[DMMessageResponse] = None

    model_config = {"from_attributes": True}


class MessageListResponse(BaseModel):
    items: List[DMMessageResponse]
    next_cursor: Optional[str] = None
    has_more: bool = False


class StoryResponse(BaseModel):
    story_id: uuid.UUID
    creator_id: uuid.UUID
    audio_url: str
    duration_seconds: float = 0.0
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class StoryListResponse(BaseModel):
    items: List[StoryResponse]
    total: int


class HealthResponse(BaseModel):
    status: str
    version: str
    components: dict

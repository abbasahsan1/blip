import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB

from blipp_common.database import Base


class Blipp(Base):
    """
    SQLAlchemy model representing a published or processing audio reel matching Section 5.3.
    """
    __tablename__ = "blipps"

    blipp_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users_profile.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    audio_url = Column(String(1024), nullable=False)
    audio_variants = Column(JSONB, nullable=False, default=dict)
    duration_seconds = Column(Float, nullable=False, default=0.0)
    language = Column(String(10), nullable=False, default="en")
    status = Column(
        String(50),
        nullable=False,
        default="processing",
        index=True,
    )
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    source_type = Column(String(50), nullable=False, default="direct_upload")
    parent_upload_id = Column(
        UUID(as_uuid=True),
        ForeignKey("uploads.upload_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class BlippSave(Base):
    """
    SQLAlchemy model representing a saved/bookmarked audio reel matching Section 5.3.
    """
    __tablename__ = "saves"

    user_id = Column(UUID(as_uuid=True), primary_key=True)
    blipp_id = Column(
        UUID(as_uuid=True),
        ForeignKey("blipps.blipp_id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "blipp_id", name="uq_user_blipp_save"),
    )


__all__ = ["Blipp", "BlippSave"]

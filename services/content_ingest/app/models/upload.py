import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from blipp_common.database import Base


class Upload(Base):
    """
    SQLAlchemy model representing an uploaded media item matching Section 5.3.
    """
    __tablename__ = "uploads"

    upload_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users_profile.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    raw_file_url = Column(String(1024), nullable=False)
    upload_type = Column(String(50), nullable=False, default="audio")
    processing_status = Column(
        String(50),
        nullable=False,
        default="queued",
        index=True,
    )
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


__all__ = ["Upload"]

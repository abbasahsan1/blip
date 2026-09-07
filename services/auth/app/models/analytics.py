import uuid
from datetime import date
from sqlalchemy import Column, Float, Boolean, Date, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class ListeningSessionAgg(Base):
    """
    SQLAlchemy model representing aggregated playback session telemetry matching Section 5.7.
    """
    __tablename__ = "listening_session_agg"

    session_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users_profile.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    blipp_id = Column(
        UUID(as_uuid=True),
        ForeignKey("blipps.blipp_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    total_seconds_listened = Column(Float, nullable=False, default=0.0)
    completed = Column(Boolean, nullable=False, default=False)
    drop_off_position_seconds = Column(Float, nullable=True)
    session_date = Column(Date, nullable=False, default=date.today)

    __table_args__ = (
        UniqueConstraint("session_id", name="uq_listening_session_id"),
    )


class CreatorMinutesAgg(Base):
    """
    SQLAlchemy model representing daily aggregated listening minutes for creators matching Section 5.7.
    """
    __tablename__ = "creator_minutes_agg"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users_profile.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    blipp_id = Column(
        UUID(as_uuid=True),
        ForeignKey("blipps.blipp_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    total_minutes_listened = Column(Float, nullable=False, default=0.0)
    date = Column(Date, nullable=False, default=date.today)

    __table_args__ = (
        UniqueConstraint("creator_id", "blipp_id", "date", name="uq_creator_blipp_date"),
    )

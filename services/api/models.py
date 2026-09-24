"""
models.py — SQLModel table definitions for Blipps v1.

Two tables only: users + blipps.

NOTE on audio_url: stores the B2 object KEY (e.g. "blipps/<uuid>.mp3"),
not the full URL. Route handlers call storage.presigned_url(key) when
building responses so URLs are always fresh (private bucket).

password_hash is write-only (never returned in API responses).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    username: str = Field(unique=True, index=True, max_length=40)
    email: str = Field(unique=True, index=True)
    password_hash: str  # bcrypt hash — never exposed in responses
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class Blipp(SQLModel, table=True):
    __tablename__ = "blipps"
    __table_args__ = {"extend_existing": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    creator_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    title: str = Field(max_length=200)
    audio_url: str  # B2 object key, e.g. "blipps/<uuid>.mp3"
    duration_seconds: Optional[float] = None
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

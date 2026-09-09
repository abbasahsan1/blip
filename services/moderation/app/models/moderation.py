import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Column, DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID

from blipp_common.database import Base


# ─── Allowed Enums / Constants (§5.5) ─────────────────────────────────────────

REPORT_REASONS = {"copyright", "harassment", "spam", "misinformation", "other"}
REPORT_STATUSES = {"open", "reviewed", "actioned", "dismissed"}
STRIKE_REASONS = {"copyright", "community_guidelines", "other"}


# ─── SQLAlchemy Declarative Models (§5.5) ──────────────────────────────────────

class Report(Base):
    """
    User Content Report record (§5.5).
    Tracks reports lodged against blipps by authenticated users.
    """
    __tablename__ = "reports"

    report_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reporter_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    blipp_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    creator_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    reason = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, default="open", index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("CURRENT_TIMESTAMP"))


class Strike(Base):
    """
    Creator Strike record (§5.5, §6.7).
    Issued when content is actioned for removal/infringement.
    """
    __tablename__ = "strikes"

    strike_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    blipp_id = Column(UUID(as_uuid=True), nullable=True)
    reason = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("CURRENT_TIMESTAMP"))


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class CreateReportRequest(BaseModel):
    blipp_id: uuid.UUID
    reason: str = Field(..., description="Report reason: 'copyright', 'harassment', 'spam', 'misinformation', 'other'")
    creator_id: Optional[uuid.UUID] = Field(default=None, description="Optional creator_id of reported blipp")

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if cleaned not in REPORT_REASONS:
            raise ValueError(f"Reason must be one of: {sorted(list(REPORT_REASONS))}")
        return cleaned


class CreateReportResponse(BaseModel):
    report_id: uuid.UUID
    status: str = "open"


class ReportResponse(BaseModel):
    report_id: uuid.UUID
    reporter_id: uuid.UUID
    blipp_id: uuid.UUID
    creator_id: Optional[uuid.UUID] = None
    reason: str
    status: str
    created_at: Optional[str] = None


class ReportsListResponse(BaseModel):
    items: List[ReportResponse] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class ActionReportRequest(BaseModel):
    action: Literal["actioned", "dismissed"] = Field(..., description="Moderation action: 'actioned' or 'dismissed'")
    reason: Optional[str] = Field(default="community_guidelines", description="Strike reason if actioned ('copyright', 'community_guidelines', 'other')")
    creator_id: Optional[uuid.UUID] = Field(default=None, description="Creator ID if known/overridden")

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if cleaned not in {"actioned", "dismissed"}:
            raise ValueError("Action must be either 'actioned' or 'dismissed'")
        return cleaned


class ActionReportResponse(BaseModel):
    report_id: uuid.UUID
    status: str
    action: str
    strike_id: Optional[uuid.UUID] = None
    creator_id: Optional[uuid.UUID] = None
    strikes_count_90d: Optional[int] = None
    account_suspended: bool = False
    message: str = "Report action processed"


class HealthResponse(BaseModel):
    status: str
    version: str

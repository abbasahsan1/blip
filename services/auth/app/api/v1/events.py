import logging
from typing import Literal
from fastapi import APIRouter, status
from pydantic import BaseModel

logger = logging.getLogger("auth-service.api.events")

router = APIRouter(prefix="/events", tags=["events"])


class PlayProgressEvent(BaseModel):
    event_type: Literal["play_progress", "play_complete", "skip", "like", "save", "follow", "share"]
    user_id: str
    blipp_id: str
    session_id: str
    position_seconds: float
    duration_seconds: float
    device_signal: Literal["screen_on", "screen_off", "bluetooth_connected", "app_backgrounded"]
    timestamp: str


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def record_event(event: PlayProgressEvent):
    """
    Ingests audio playback telemetry and returns 202 Accepted.
    """
    logger.info(
        f"Telemetry event [202]: type={event.event_type} blipp_id={event.blipp_id} "
        f"pos={event.position_seconds}/{event.duration_seconds}s signal={event.device_signal}"
    )
    return {"status": "accepted"}

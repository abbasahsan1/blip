import re
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import BaseModel, Field

from blipp_common.events import event_bus
from blipp_common.security import AuthenticatedUser, get_current_user

router = APIRouter(tags=["Engagement Events"])
_EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class EngagementEvent(BaseModel):
    event_type: str = Field(min_length=1, max_length=64)
    blipp_id: str
    session_id: str
    position_seconds: float = 0
    duration_seconds: float = 0
    device_signal: str | None = None
    timestamp: str | None = None


async def publish_events(events: List[EngagementEvent], user_id: str) -> None:
    for event in events:
        if not _EVENT_TYPE.fullmatch(event.event_type):
            continue
        payload = event.model_dump()
        payload["user_id"] = user_id
        await event_bus.publish(f"engagement.{event.event_type}", payload)


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def ingest_events(
    events: List[EngagementEvent],
    background_tasks: BackgroundTasks,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Acknowledge a client batch immediately and publish it to JetStream."""
    background_tasks.add_task(publish_events, events, str(current_user.user_id))
    return {"accepted": len(events)}

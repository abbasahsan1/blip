import asyncio
import logging
from typing import List, Union
from fastapi import APIRouter, Body, status

from app.core.events import event_bus
from app.models.schemas import EngagementEvent

logger = logging.getLogger("auth-service.api.events")

router = APIRouter(prefix="/events", tags=["Engagement Events"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
@router.post("/", status_code=status.HTTP_202_ACCEPTED)
async def record_events(
    payload: Union[EngagementEvent, List[EngagementEvent]] = Body(...),
):
    """
    Asynchronous event ingestion conforming to Section 5.8.
    Supports single events or batch event lists.
    Publishes onto NATS JetStream ENGAGEMENT stream with subject engagement.<event_type>.
    Fire-and-forget: returns HTTP 202 Accepted immediately.
    """
    events = [payload] if isinstance(payload, EngagementEvent) else payload

    publish_tasks = [
        event_bus.publish(
            subject=f"engagement.{event.event_type}",
            payload={
                "event_type": event.event_type,
                "user_id": str(event.user_id),
                "blipp_id": str(event.blipp_id),
                "session_id": str(event.session_id),
                "position_seconds": event.position_seconds,
                "duration_seconds": event.duration_seconds,
                "device_signal": event.device_signal,
                "timestamp": event.timestamp,
            },
        )
        for event in events
    ]

    if publish_tasks:
        try:
            await asyncio.gather(*publish_tasks, return_exceptions=True)
        except Exception as e:
            logger.warning(f"Error publishing engagement events to NATS: {e}")

    return {"status": "accepted", "count": len(events)}

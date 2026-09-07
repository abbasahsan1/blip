"""
NATS JetStream event bus integration for auth service, consuming blipp_common.events.
"""

from blipp_common.events import EventBus
from app.core.config import settings

event_bus = EventBus(settings=settings)

__all__ = ["EventBus", "event_bus"]

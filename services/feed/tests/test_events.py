import os
import sys
import uuid
import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

# App module path resolution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from blipp_common.security import get_current_user, AuthenticatedUser

client = TestClient(app)
TEST_USER_ID = str(uuid.uuid4())

def override_get_current_user():
    return AuthenticatedUser(user_id=TEST_USER_ID, roles=["user"], username="testuser")

app.dependency_overrides[get_current_user] = override_get_current_user


def test_ingest_events():
    payload = [
        {
            "event_type": "play",
            "blipp_id": str(uuid.uuid4()),
            "session_id": str(uuid.uuid4()),
            "position_seconds": 10.5,
            "duration_seconds": 60.0,
            "device_signal": "ios"
        },
        {
            "event_type": "pause",
            "blipp_id": str(uuid.uuid4()),
            "session_id": str(uuid.uuid4()),
            "position_seconds": 25.0,
            "duration_seconds": 60.0,
        }
    ]

    with patch("app.api.v1.events.event_bus.publish", new_callable=AsyncMock) as mock_publish:
        response = client.post("/v1/events", json=payload)
        
        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 2
        
        # TestClient blocks on background tasks if they are executed locally,
        # so we can assert on the mock directly.
        assert mock_publish.call_count == 2
        calls = mock_publish.call_args_list
        assert calls[0][0][0] == "engagement.play"
        assert calls[0][0][1]["user_id"] == TEST_USER_ID
        assert calls[1][0][0] == "engagement.pause"
        assert calls[1][0][1]["user_id"] == TEST_USER_ID


def test_ingest_events_invalid_type():
    payload = [
        {
            "event_type": "123invalid",
            "blipp_id": str(uuid.uuid4()),
            "session_id": str(uuid.uuid4()),
        }
    ]

    with patch("app.api.v1.events.event_bus.publish", new_callable=AsyncMock) as mock_publish:
        response = client.post("/v1/events", json=payload)
        
        assert response.status_code == 202
        
        # Should not publish invalid event types
        assert mock_publish.call_count == 0

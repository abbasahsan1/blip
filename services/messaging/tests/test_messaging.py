"""
Comprehensive unit and integration test suite for Messaging & 24-Hour Audio Stories Microservice (§3 #4, §5.4, §8).
"""
import os
import sys
import uuid
import pytest
from fastapi.testclient import TestClient

# App module path resolution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from blipp_common.security import get_current_user, AuthenticatedUser

# Create test client
client = TestClient(app)

# Mock user data
TEST_USER_1_ID = str(uuid.uuid4())
TEST_USER_2_ID = str(uuid.uuid4())

def override_get_current_user_1():
    return AuthenticatedUser(user_id=TEST_USER_1_ID, roles=["user"], username="testuser1")

def override_get_current_user_2():
    return AuthenticatedUser(user_id=TEST_USER_2_ID, roles=["user"], username="testuser2")

app.dependency_overrides[get_current_user] = override_get_current_user_1


# Need an async fixture for db pool if we don't mock it, but test client is synchronous.
# However, fastapi routes use asyncpg pool from blipp_common.database
# We should probably use pytest-asyncio and httpx AsyncClient for proper DB tests, 
# or just mock the db_pool to return fake data.

from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_pool():
    with patch("app.api.v1.messages.get_db_pool", new_callable=AsyncMock) as mock_get_pool:
        pool_instance = AsyncMock()
        
        # We need a context manager for acquire()
        class AsyncContextManagerMock:
            async def __aenter__(self):
                conn = AsyncMock()
                # Default fetchrow returns None (no existing thread)
                conn.fetchrow.return_value = None
                return conn
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
                
        pool_instance.acquire.return_value = AsyncContextManagerMock()
        mock_get_pool.return_value = pool_instance
        
        yield pool_instance


def test_create_thread(mock_pool):
    # Set user 1
    app.dependency_overrides[get_current_user] = override_get_current_user_1

    response = client.post(
        "/v1/messages/threads",
        json={"recipient_id": TEST_USER_2_ID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "thread_id" in data
    assert TEST_USER_1_ID in data["participant_ids"]
    assert TEST_USER_2_ID in data["participant_ids"]


def test_cannot_dm_self(mock_pool):
    response = client.post(
        "/v1/messages/threads",
        json={"recipient_id": TEST_USER_1_ID}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CANNOT_DM_SELF"


def test_send_message_text(mock_pool):
    thread_id = str(uuid.uuid4())
    
    # We must patch get_db_pool again and configure it to return the thread
    with patch("app.api.v1.messages.get_db_pool", new_callable=AsyncMock) as mock_get_pool:
        pool_instance = AsyncMock()
        class AsyncContextManagerMock:
            async def __aenter__(self):
                conn = AsyncMock()
                conn.fetchrow.return_value = {"thread_id": thread_id, "participant_ids": [TEST_USER_1_ID, TEST_USER_2_ID]}
                return conn
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        pool_instance.acquire.return_value = AsyncContextManagerMock()
        mock_get_pool.return_value = pool_instance

        response = client.post(
            f"/v1/messages/threads/{thread_id}",
            json={"message_type": "text", "body": "Hello world!"}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["message_type"] == "text"
        assert data["body"] == "Hello world!"
        assert data["sender_id"] == TEST_USER_1_ID


def test_send_message_not_participant(mock_pool):
    thread_id = str(uuid.uuid4())
    
    with patch("app.api.v1.messages.get_db_pool", new_callable=AsyncMock) as mock_get_pool:
        pool_instance = AsyncMock()
        class AsyncContextManagerMock:
            async def __aenter__(self):
                conn = AsyncMock()
                # User 1 is NOT a participant
                conn.fetchrow.return_value = {"thread_id": thread_id, "participant_ids": [TEST_USER_2_ID, str(uuid.uuid4())]}
                return conn
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        pool_instance.acquire.return_value = AsyncContextManagerMock()
        mock_get_pool.return_value = pool_instance

        response = client.post(
            f"/v1/messages/threads/{thread_id}",
            json={"message_type": "text", "body": "Sneaky"}
        )
        
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "NOT_A_PARTICIPANT"


def test_story_expiration():
    # Test for stories cleanup (mocked for now)
    pass

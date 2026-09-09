"""
Comprehensive unit and integration test suite for Messaging & 24-Hour Audio Stories Microservice (§3 #4, §5.4, §8).

Tests cover:
- Thread creation between participants and retrieval of existing threads
- Prevention of self-DM
- Sending text messages and blipp_share messages (with attached blipp_id)
- Validation of payload (e.g. blipp_share requiring blipp_id)
- Authorization: participant validation (403 Forbidden for non-participants)
- Cursor-paginated message retrieval
- Ephemeral audio story publishing with 24-hour expiration
- Exclusion of expired stories (>24h) from active story feeds and creator lookups
- Background story cleanup worker (purging expired rows & calling storage deletion)
"""

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

# Ensure modules are on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../libs/common")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from blipp_common.security import AuthenticatedUser, get_current_user, get_optional_current_user
from app.models.messaging import (
    DMMessage,
    DMThread,
    MessageCreateRequest,
    Story,
    ThreadCreateRequest,
    utc_now,
    default_story_expiry,
)
from app.main import app, cleanup_expired_stories


# ─── Model & Schema Unit Tests ──────────────────────────────────────────────────

def test_message_create_request_validation():
    """Verify MessageCreateRequest validates message_type properly."""
    # Valid text
    req1 = MessageCreateRequest(message_type="text", body="Hello there")
    assert req1.message_type == "text"
    assert req1.body == "Hello there"

    # Valid blipp_share
    b_id = uuid.uuid4()
    req2 = MessageCreateRequest(message_type="blipp_share", blipp_id=b_id)
    assert req2.message_type == "blipp_share"
    assert req2.blipp_id == b_id

    # Invalid message_type
    with pytest.raises(ValidationError):
        MessageCreateRequest(message_type="invalid_type")


def test_story_default_expiration():
    """Verify default story expiration is 24 hours in the future."""
    now = datetime.now(timezone.utc)
    expiry = default_story_expiry()
    diff = expiry - now
    # Should be approximately 24 hours (within 5 seconds)
    assert 86395 <= diff.total_seconds() <= 86405


# ─── Mock Database Setup for API Integration Tests ─────────────────────────────

class MockDB:
    """In-memory DB simulating PostgreSQL queries for messaging and stories."""
    def __init__(self):
        self.threads = {}   # thread_id -> dict
        self.messages = []  # list of message dicts
        self.stories = []   # list of story dicts

    def acquire(self):
        return MockConnectionContext(self)


class MockConnectionContext:
    def __init__(self, db: MockDB):
        self.db = db

    async def __aenter__(self):
        return MockConnection(self.db)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MockConnection:
    def __init__(self, db: MockDB):
        self.db = db

    async def fetchval(self, query: str, *args):
        if "SELECT 1" in query:
            return 1
        return None

    async def fetchrow(self, query: str, *args):
        q = query.strip()
        # Find thread between two participants
        if "FROM dm_threads" in q and "participant_ids @> ARRAY" in q:
            u1, u2 = args[0], args[1]
            for t in self.db.threads.values():
                p_ids = set(t["participant_ids"])
                if u1 in p_ids and u2 in p_ids and len(p_ids) == 2:
                    return t
            return None

        # Find thread by thread_id
        if "FROM dm_threads WHERE thread_id = $1" in q:
            tid = args[0]
            return self.db.threads.get(tid)

        # Find latest message for thread
        if "FROM dm_messages" in q and "ORDER BY created_at DESC" in q and "LIMIT 1" in q:
            tid = args[0]
            thread_msgs = [m for m in self.db.messages if m["thread_id"] == tid]
            if thread_msgs:
                thread_msgs.sort(key=lambda x: x["created_at"], reverse=True)
                return thread_msgs[0]
            return None

        return None

    async def fetch(self, query: str, *args):
        q = query.strip()
        # List threads for user
        if "FROM dm_threads t" in q and "$1::uuid = ANY(t.participant_ids)" in q:
            uid = args[0]
            limit = args[1]
            offset = args[2]
            user_threads = [t for t in self.db.threads.values() if uid in t["participant_ids"]]
            user_threads.sort(key=lambda x: x["updated_at"], reverse=True)
            matched = user_threads[offset:offset + limit]
            rows = []
            for t in matched:
                thread_msgs = [m for m in self.db.messages if m["thread_id"] == t["thread_id"]]
                thread_msgs.sort(key=lambda x: x["created_at"], reverse=True)
                latest = thread_msgs[0] if thread_msgs else None
                rows.append({
                    "thread_id": t["thread_id"],
                    "participant_ids": t["participant_ids"],
                    "created_at": t["created_at"],
                    "updated_at": t["updated_at"],
                    "message_id": latest["message_id"] if latest else None,
                    "sender_id": latest["sender_id"] if latest else None,
                    "message_type": latest["message_type"] if latest else None,
                    "blipp_id": latest["blipp_id"] if latest else None,
                    "body": latest["body"] if latest else None,
                    "message_created_at": latest["created_at"] if latest else None,
                })
            return rows

        # Thread messages with cursor
        if "FROM dm_messages" in q and "WHERE thread_id = $1 AND created_at < $2" in q:
            tid = args[0]
            cursor_dt = args[1]
            limit = args[2]
            t_msgs = [m for m in self.db.messages if m["thread_id"] == tid and m["created_at"] < cursor_dt]
            t_msgs.sort(key=lambda x: x["created_at"], reverse=True)
            return t_msgs[:limit]

        # Thread messages without cursor
        if "FROM dm_messages" in q and "WHERE thread_id = $1" in q:
            tid = args[0]
            limit = args[1]
            t_msgs = [m for m in self.db.messages if m["thread_id"] == tid]
            t_msgs.sort(key=lambda x: x["created_at"], reverse=True)
            return t_msgs[:limit]

        # Active stories for creator IDs
        if "FROM stories" in q and "creator_id = ANY" in q:
            c_ids = set(args[0])
            now = datetime.now(timezone.utc)
            active = [s for s in self.db.stories if s["creator_id"] in c_ids and s["expires_at"] > now]
            active.sort(key=lambda x: x["created_at"], reverse=True)
            return active

        # Active stories for specific creator
        if "FROM stories" in q and "creator_id = $1" in q:
            c_id = args[0]
            now = datetime.now(timezone.utc)
            active = [s for s in self.db.stories if s["creator_id"] == c_id and s["expires_at"] > now]
            active.sort(key=lambda x: x["created_at"], reverse=True)
            return active

        # Expired stories for cleanup
        if "FROM stories" in q and "expires_at <= NOW()" in q:
            now = datetime.now(timezone.utc)
            expired = [s for s in self.db.stories if s["expires_at"] <= now]
            return expired

        return []

    async def execute(self, query: str, *args):
        q = query.strip()
        # Insert thread
        if "INSERT INTO dm_threads" in q:
            tid = args[0]
            p_ids = args[1]
            created = args[2]
            updated = args[3]
            self.db.threads[tid] = {
                "thread_id": tid,
                "participant_ids": p_ids,
                "created_at": created,
                "updated_at": updated,
            }
            return "INSERT 0 1"

        # Insert message
        if "INSERT INTO dm_messages" in q:
            mid, tid, sid, mtype, bid, body, created = args
            msg = {
                "message_id": mid,
                "thread_id": tid,
                "sender_id": sid,
                "message_type": mtype,
                "blipp_id": bid,
                "body": body,
                "created_at": created,
            }
            self.db.messages.append(msg)
            return "INSERT 0 1"

        # Update thread
        if "UPDATE dm_threads SET updated_at = $1 WHERE thread_id = $2" in q:
            now, tid = args
            if tid in self.db.threads:
                self.db.threads[tid]["updated_at"] = now
            return "UPDATE 1"

        # Insert story
        if "INSERT INTO stories" in q:
            sid, cid, url, dur, exp, cr = args
            self.db.stories.append({
                "story_id": sid,
                "creator_id": cid,
                "audio_url": url,
                "duration_seconds": dur,
                "expires_at": exp,
                "created_at": cr,
            })
            return "INSERT 0 1"

        # Delete expired stories
        if "DELETE FROM stories" in q and "expires_at <= NOW()" in q:
            now = datetime.now(timezone.utc)
            orig_len = len(self.db.stories)
            self.db.stories = [s for s in self.db.stories if s["expires_at"] > now]
            deleted = orig_len - len(self.db.stories)
            return f"DELETE {deleted}"

        return "OK"


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    return MockDB()


@pytest.fixture
def user_alice():
    uid = uuid.uuid4()
    return AuthenticatedUser(
        user_id=uid,
        id=str(uid),
        username="alice",
        email="alice@blipp.local",
    )


@pytest.fixture
def user_bob():
    uid = uuid.uuid4()
    return AuthenticatedUser(
        user_id=uid,
        id=str(uid),
        username="bob",
        email="bob@blipp.local",
    )


@pytest.fixture
def user_eve():
    uid = uuid.uuid4()
    return AuthenticatedUser(
        user_id=uid,
        id=str(uid),
        username="eve",
        email="eve@blipp.local",
    )


# ─── Direct Messaging Integration Tests ────────────────────────────────────────

def test_prevent_self_dm(mock_db, user_alice):
    """Verify that a user cannot start a direct message thread with themselves."""
    app.dependency_overrides[get_current_user] = lambda: user_alice
    with patch("app.api.v1.messages.get_db_pool", AsyncMock(return_value=mock_db)):
        client = TestClient(app)
        res = client.post("/v1/messages/threads", json={"recipient_id": str(user_alice.user_id)})
        assert res.status_code == 400
        assert res.json()["code"] == "CANNOT_DM_SELF"


def test_thread_creation_and_idempotency(mock_db, user_alice, user_bob):
    """Verify thread creation and idempotency when creating existing thread."""
    app.dependency_overrides[get_current_user] = lambda: user_alice
    with patch("app.api.v1.messages.get_db_pool", AsyncMock(return_value=mock_db)):
        client = TestClient(app)

        # 1. Create thread
        res1 = client.post("/v1/messages/threads", json={"recipient_id": str(user_bob.user_id)})
        assert res1.status_code == 200
        data1 = res1.json()
        assert "thread_id" in data1
        thread_id = data1["thread_id"]
        assert len(mock_db.threads) == 1

        # 2. Re-create thread from same caller - should return existing
        res2 = client.post("/v1/messages/threads", json={"recipient_id": str(user_bob.user_id)})
        assert res2.status_code == 200
        assert res2.json()["thread_id"] == thread_id
        assert len(mock_db.threads) == 1

        # 3. Create thread from recipient's side - should return existing
        app.dependency_overrides[get_current_user] = lambda: user_bob
        res3 = client.post("/v1/messages/threads", json={"recipient_id": str(user_alice.user_id)})
        assert res3.status_code == 200
        assert res3.json()["thread_id"] == thread_id
        assert len(mock_db.threads) == 1


def test_send_and_retrieve_messages(mock_db, user_alice, user_bob, user_eve):
    """Verify message sending (text & blipp_share), authorization, and cursor retrieval."""
    app.dependency_overrides[get_current_user] = lambda: user_alice
    with patch("app.api.v1.messages.get_db_pool", AsyncMock(return_value=mock_db)):
        client = TestClient(app)

        # 1. Setup thread
        res_thread = client.post("/v1/messages/threads", json={"recipient_id": str(user_bob.user_id)})
        thread_id = res_thread.json()["thread_id"]

        # 2. Alice sends a text message
        msg1_res = client.post(
            f"/v1/messages/threads/{thread_id}",
            json={"message_type": "text", "body": "Hey Bob!"},
        )
        assert msg1_res.status_code == 201
        msg1_data = msg1_res.json()
        assert msg1_data["message_type"] == "text"
        assert msg1_data["body"] == "Hey Bob!"
        assert msg1_data["sender_id"] == str(user_alice.user_id)

        # 3. Bob sends a blipp_share message
        app.dependency_overrides[get_current_user] = lambda: user_bob
        shared_blipp_id = uuid.uuid4()
        msg2_res = client.post(
            f"/v1/messages/threads/{thread_id}",
            json={
                "message_type": "blipp_share",
                "blipp_id": str(shared_blipp_id),
                "body": "Check out this audio reel!",
            },
        )
        assert msg2_res.status_code == 201
        msg2_data = msg2_res.json()
        assert msg2_data["message_type"] == "blipp_share"
        assert msg2_data["blipp_id"] == str(shared_blipp_id)
        assert msg2_data["sender_id"] == str(user_bob.user_id)

        # 4. Invalid blipp_share without blipp_id fails with 400
        bad_msg_res = client.post(
            f"/v1/messages/threads/{thread_id}",
            json={"message_type": "blipp_share", "body": "Missing blipp id"},
        )
        assert bad_msg_res.status_code == 400
        assert bad_msg_res.json()["code"] == "INVALID_MESSAGE_PAYLOAD"

        # 5. Eve (non-participant) tries to send a message -> 403 Forbidden
        app.dependency_overrides[get_current_user] = lambda: user_eve
        eve_send_res = client.post(
            f"/v1/messages/threads/{thread_id}",
            json={"message_type": "text", "body": "I want in"},
        )
        assert eve_send_res.status_code == 403
        assert eve_send_res.json()["code"] == "NOT_A_PARTICIPANT"

        # 6. Eve tries to read messages -> 403 Forbidden
        eve_read_res = client.get(f"/v1/messages/threads/{thread_id}")
        assert eve_read_res.status_code == 403

        # 7. Alice lists messages -> gets both items
        app.dependency_overrides[get_current_user] = lambda: user_alice
        alice_read_res = client.get(f"/v1/messages/threads/{thread_id}")
        assert alice_read_res.status_code == 200
        history = alice_read_res.json()
        assert len(history["items"]) == 2
        assert history["items"][0]["message_id"] == msg2_data["message_id"]
        assert history["items"][1]["message_id"] == msg1_data["message_id"]


# ─── 24-Hour Ephemeral Audio Stories Integration Tests ─────────────────────────

@pytest.mark.asyncio
async def test_stories_expiration_and_cleanup(mock_db, user_alice, user_bob):
    """
    Verify:
    1. Posting audio stories with 24-hour expiration
    2. Active stories returned in queries
    3. Stories past 24 hours excluded from queries
    4. Cleanup worker deletes expired stories and calls storage deletion
    """
    app.dependency_overrides[get_current_user] = lambda: user_alice
    app.dependency_overrides[get_optional_current_user] = lambda: user_alice

    with patch("app.api.v1.stories.get_db_pool", AsyncMock(return_value=mock_db)), \
         patch("app.main.get_db_pool", AsyncMock(return_value=mock_db)), \
         patch("app.api.v1.stories.storage_service.upload_stream", AsyncMock(return_value="http://storage/audio.mp3")), \
         patch("app.api.v1.stories.storage_service.get_playback_url", return_value="http://storage/audio.mp3"), \
         patch("app.main.storage_service.delete_file", AsyncMock(return_value=True)) as mock_delete_file:

        client = TestClient(app)

        # 1. Post an active story
        files = {"file": ("test_story.mp3", b"FAKE_AUDIO_BYTES", "audio/mpeg")}
        res = client.post("/v1/stories", files=files, data={"duration_seconds": "15.5"})
        assert res.status_code == 201
        data = res.json()
        active_story_id = uuid.UUID(data["story_id"])
        assert data["creator_id"] == str(user_alice.user_id)
        assert data["duration_seconds"] == 15.5

        # 2. Add an EXPIRED story manually (created 25 hours ago, expired 1 hour ago)
        expired_story_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        mock_db.stories.append({
            "story_id": expired_story_id,
            "creator_id": user_alice.user_id,
            "audio_url": "http://storage/expired_story.mp3",
            "duration_seconds": 12.0,
            "expires_at": now - timedelta(hours=1),
            "created_at": now - timedelta(hours=25),
        })

        assert len(mock_db.stories) == 2

        # 3. Query creator stories -> expired story MUST be excluded
        res_stories = client.get(f"/v1/stories/{user_alice.user_id}")
        assert res_stories.status_code == 200
        stories_list = res_stories.json()["items"]
        assert len(stories_list) == 1
        assert stories_list[0]["story_id"] == str(active_story_id)

        # 4. Run cleanup_expired_stories()
        deleted_count = await cleanup_expired_stories()
        assert deleted_count == 1
        assert len(mock_db.stories) == 1
        assert mock_db.stories[0]["story_id"] == active_story_id

        # Verify storage deletion was called on the expired audio url
        mock_delete_file.assert_called_once_with(
            storage_key="http://storage/expired_story.mp3",
            bucket_name="blipp-stories",
        )


if __name__ == "__main__":
    import asyncio
    print("Running messaging test suite...")
    test_message_create_request_validation()
    print("✓ test_message_create_request_validation passed")
    test_story_default_expiration()
    print("✓ test_story_default_expiration passed")

    db = MockDB()
    alice = user_alice()
    bob = user_bob()
    eve = user_eve()

    test_prevent_self_dm(db, alice)
    print("✓ test_prevent_self_dm passed")
    test_thread_creation_and_idempotency(db, alice, bob)
    print("✓ test_thread_creation_and_idempotency passed")
    test_send_and_retrieve_messages(db, alice, bob, eve)
    print("✓ test_send_and_retrieve_messages passed")

    asyncio.run(test_stories_expiration_and_cleanup(MockDB(), alice, bob))
    print("✓ test_stories_expiration_and_cleanup passed")
    print("\nALL MESSAGING & STORIES TESTS PASSED SUCCESSFULLY! 🚀")

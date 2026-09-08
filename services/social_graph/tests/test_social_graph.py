"""
Comprehensive unit and integration test suite for Social Graph Service (§5.2 & §6.1).
Tests:
- Username claim validation (§6.1)
- 409 Conflict on duplicate username / already-claimed profile
- Profile retrieval & updates
- Public profile lookup with social counts & is_following
- Self-follow prevention
- Follow & unfollow lifecycle with follower count increment/decrement (§5.2)
- NATS JetStream engagement event publishing (§5.8)
"""

import uuid
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.models.profile import (
    ProfileCreate,
    ProfileUpdate,
    ProfileResponse,
    FollowActionResponse,
)


def test_profile_create_validation():
    """Verify username validation rules (3-30 chars, alphanumeric + underscores, lowercased)."""
    # Valid usernames
    p1 = ProfileCreate(username="alice", display_name="Alice")
    assert p1.username == "alice"

    p2 = ProfileCreate(username="John_Doe_99")
    assert p2.username == "john_doe_99"

    p3 = ProfileCreate(username="   user_abc   ")
    assert p3.username == "user_abc"

    # Too short (< 3 chars)
    with pytest.raises(ValidationError):
        ProfileCreate(username="ab")

    # Too long (> 30 chars)
    with pytest.raises(ValidationError):
        ProfileCreate(username="a" * 31)

    # Invalid characters (spaces, special symbols)
    with pytest.raises(ValidationError):
        ProfileCreate(username="user-name")

    with pytest.raises(ValidationError):
        ProfileCreate(username="user@name")

    with pytest.raises(ValidationError):
        ProfileCreate(username="user name")


def test_profile_update_schema():
    """Verify ProfileUpdate optional field handling."""
    update = ProfileUpdate(display_name="New Name", bio="Hello world")
    assert update.display_name == "New Name"
    assert update.bio == "Hello world"
    assert update.avatar_url is None


def test_profile_response_schema():
    """Verify ProfileResponse computed attributes."""
    uid = uuid.uuid4()
    resp = ProfileResponse(
        user_id=uid,
        username="test_user",
        display_name="Test User",
        followers_count=5,
        following_count=12,
        is_following=True,
    )
    assert resp.user_id == uid
    assert resp.followers_count == 5
    assert resp.following_count == 12
    assert resp.is_following is True


# ─── Mock-based API Endpoint Integration Tests ─────────────────────────────────

from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from blipp_common.security import get_current_user, get_optional_current_user, AuthenticatedUser
from app.main import app


@pytest.fixture
def mock_user_alice():
    uid = uuid.uuid4()
    return AuthenticatedUser(
        user_id=uid,
        id=str(uid),
        username="alice",
        email="alice@blipp.local",
        first_name="Alice",
    )


@pytest.fixture
def mock_user_bob():
    uid = uuid.uuid4()
    return AuthenticatedUser(
        user_id=uid,
        id=str(uid),
        username="bob",
        email="bob@blipp.local",
        first_name="Bob",
    )


class MockDatabasePool:
    """In-memory mock database pool simulating asyncpg queries for social graph."""
    def __init__(self):
        self.users = {}       # user_id -> dict
        self.usernames = {}   # username.lower() -> user_id
        self.follows = set()  # (follower_id, followee_id)

    def acquire(self):
        return MockConnectionContext(self)


class MockConnectionContext:
    def __init__(self, db: MockDatabasePool):
        self.db = db

    async def __aenter__(self):
        return MockConnection(self.db)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MockConnection:
    def __init__(self, db: MockDatabasePool):
        self.db = db

    async def fetchrow(self, query: str, *args):
        q = query.strip().upper()
        if "FROM USERS_PROFILE WHERE USER_ID = $1" in q:
            uid = args[0]
            if uid in self.db.users:
                u = self.db.users[uid]
                return {
                    "user_id": u["user_id"],
                    "username": u["username"],
                    "display_name": u["display_name"],
                    "bio": u["bio"],
                    "avatar_url": u["avatar_url"],
                    "is_creator": u.get("is_creator", False),
                    "verification_status": u.get("verification_status", "unverified"),
                    "created_at": u.get("created_at", datetime.now(timezone.utc)),
                }
            return None

        if "FROM USERS_PROFILE WHERE LOWER(USERNAME) = $1" in q:
            uname = str(args[0]).lower()
            if uname in self.db.usernames:
                uid = self.db.usernames[uname]
                u = self.db.users[uid]
                return {
                    "user_id": u["user_id"],
                    "username": u["username"],
                    "display_name": u["display_name"],
                    "bio": u["bio"],
                    "avatar_url": u["avatar_url"],
                    "is_creator": u.get("is_creator", False),
                    "verification_status": u.get("verification_status", "unverified"),
                    "created_at": u.get("created_at", datetime.now(timezone.utc)),
                }
            return None

        if "INSERT INTO USERS_PROFILE" in q:
            uid, uname, dname = args[0], args[1], args[2]
            bio = args[3] if len(args) > 3 else None
            avatar = args[4] if len(args) > 4 else None
            self.db.users[uid] = {
                "user_id": uid,
                "username": uname,
                "display_name": dname,
                "bio": bio,
                "avatar_url": avatar,
                "is_creator": False,
                "verification_status": "unverified",
                "created_at": datetime.now(timezone.utc),
            }
            self.db.usernames[uname.lower()] = uid
            return self.db.users[uid]

        if "UPDATE USERS_PROFILE" in q:
            uid = args[-1]
            u = self.db.users.get(uid)
            if u:
                if len(args) > 1 and args[0] is not None:
                    u["display_name"] = args[0]
                return u
            return None

        return None

    async def fetchval(self, query: str, *args):
        q = query.strip().upper()
        if "COUNT(*) FROM FOLLOWS WHERE FOLLOWEE_ID = $1" in q:
            target_id = args[0]
            return sum(1 for (f, e) in self.db.follows if e == target_id)

        if "COUNT(*) FROM FOLLOWS WHERE FOLLOWER_ID = $1" in q:
            target_id = args[0]
            return sum(1 for (f, e) in self.db.follows if f == target_id)

        if "SELECT 1 FROM FOLLOWS WHERE FOLLOWER_ID = $1 AND FOLLOWEE_ID = $2" in q:
            return 1 if (args[0], args[1]) in self.db.follows else 0

        if "SELECT 1" in q:
            return 1

        return 0

    async def fetch(self, query: str, *args):
        q = query.strip().upper()
        if "WHERE F.FOLLOWEE_ID = $1" in q:
            target_id = args[0]
            rows = []
            for (f, e) in self.db.follows:
                if e == target_id and f in self.db.users:
                    u = self.db.users[f]
                    rows.append({
                        "user_id": u["user_id"],
                        "username": u["username"],
                        "display_name": u["display_name"],
                        "bio": u["bio"],
                        "avatar_url": u["avatar_url"],
                        "is_creator": u["is_creator"],
                        "verification_status": u["verification_status"],
                        "followed_at": datetime.now(timezone.utc),
                    })
            return rows

        if "WHERE F.FOLLOWER_ID = $1" in q:
            target_id = args[0]
            rows = []
            for (f, e) in self.db.follows:
                if f == target_id and e in self.db.users:
                    u = self.db.users[e]
                    rows.append({
                        "user_id": u["user_id"],
                        "username": u["username"],
                        "display_name": u["display_name"],
                        "bio": u["bio"],
                        "avatar_url": u["avatar_url"],
                        "is_creator": u["is_creator"],
                        "verification_status": u["verification_status"],
                        "followed_at": datetime.now(timezone.utc),
                    })
            return rows

        return []

    async def execute(self, query: str, *args):
        q = query.strip().upper()
        if "INSERT INTO FOLLOWS" in q:
            follower_id, followee_id = args[0], args[1]
            pair = (follower_id, followee_id)
            if pair in self.db.follows:
                return "INSERT 0 0"
            self.db.follows.add(pair)
            return "INSERT 0 1"

        if "DELETE FROM FOLLOWS" in q:
            follower_id, followee_id = args[0], args[1]
            self.db.follows.discard((follower_id, followee_id))
            return "DELETE 1"

        if "INSERT INTO USERS_PROFILE" in q:
            uid, uname, dname = args[0], args[1], args[2]
            if uid not in self.db.users:
                self.db.users[uid] = {
                    "user_id": uid,
                    "username": uname,
                    "display_name": dname,
                    "bio": None,
                    "avatar_url": None,
                    "is_creator": False,
                    "verification_status": "unverified",
                    "created_at": datetime.now(timezone.utc),
                }
                self.db.usernames[uname.lower()] = uid
            return "INSERT 0 1"

        return "OK"


def test_full_social_graph_flow(mock_user_alice, mock_user_bob):
    """
    Simulates end-to-end user lifecycle:
    1. First login username claiming (POST /v1/profiles)
    2. Conflict detection on duplicate username (409)
    3. Profile inspection (GET /v1/profiles/me)
    4. Profile update (PATCH /v1/profiles/me)
    5. Follow flow (POST /v1/social/follow/{bob_id}) & self-follow prevention (400)
    6. Follower / Following count verification
    7. Unfollow flow (DELETE /v1/social/follow/{bob_id})
    """
    mock_db = MockDatabasePool()
    current_mock_user = [mock_user_alice]

    def mock_get_current_user():
        return current_mock_user[0]

    def mock_get_optional_user():
        return current_mock_user[0]

    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_optional_current_user] = mock_get_optional_user

    with patch("app.api.v1.profiles.get_db_pool", AsyncMock(return_value=mock_db)), \
         patch("app.api.v1.relationships.get_db_pool", AsyncMock(return_value=mock_db)), \
         patch("app.main.get_db_pool", AsyncMock(return_value=mock_db)), \
         patch("app.api.v1.relationships.event_bus.publish", AsyncMock()) as mock_nats_publish:

        client = TestClient(app)

        # ── 1. Health checks ──────────────────────────────────────────────────
        health_res = client.get("/healthz")
        assert health_res.status_code == 200
        assert health_res.json()["status"] == "healthy"

        # ── 2. First-login username claiming (§6.1) ───────────────────────────
        claim_res = client.post("/v1/profiles", json={
            "username": "alice_prime",
            "display_name": "Alice Operator",
            "bio": "Audio enthusiast",
        })
        assert claim_res.status_code == 201
        data = claim_res.json()
        assert data["username"] == "alice_prime"
        assert data["display_name"] == "Alice Operator"
        assert data["followers_count"] == 0
        assert data["following_count"] == 0

        # ── 3. Duplicate username conflict (409 Conflict) ─────────────────────
        # Switch to Bob attempting to claim the same username
        current_mock_user[0] = mock_user_bob
        dup_res = client.post("/v1/profiles", json={
            "username": "ALICE_PRIME",  # case-insensitive check
            "display_name": "Imposter",
        })
        assert dup_res.status_code == 409
        assert dup_res.json()["error"]["code"] == "USERNAME_TAKEN"

        # Bob claims his own unique username
        bob_res = client.post("/v1/profiles", json={
            "username": "bob_creator",
            "display_name": "Bob Creator",
        })
        assert bob_res.status_code == 201
        bob_id = str(mock_user_bob.user_id)

        # ── 4. Profile retrieval (/v1/profiles/me) ────────────────────────────
        me_res = client.get("/v1/profiles/me")
        assert me_res.status_code == 200
        assert me_res.json()["username"] == "bob_creator"

        # ── 5. Profile update (PATCH /v1/profiles/me) ─────────────────────────
        patch_res = client.patch("/v1/profiles/me", json={
            "display_name": "Bob The Builder",
            "bio": "Architecting sound",
        })
        assert patch_res.status_code == 200
        assert patch_res.json()["display_name"] == "Bob The Builder"
        assert patch_res.json()["bio"] == "Architecting sound"

        # ── 6. Self-follow prevention ─────────────────────────────────────────
        self_follow_res = client.post(f"/v1/social/follow/{bob_id}")
        assert self_follow_res.status_code == 400
        assert self_follow_res.json()["error"]["code"] == "SELF_FOLLOW_FORBIDDEN"

        # ── 7. Follow user: Alice follows Bob ─────────────────────────────────
        current_mock_user[0] = mock_user_alice
        follow_res = client.post(f"/v1/social/follow/{bob_id}")
        assert follow_res.status_code == 200
        assert follow_res.json()["is_following"] is True

        # Verify NATS event published (§5.8)
        mock_nats_publish.assert_called_once()
        call_subject, call_payload = mock_nats_publish.call_args[0]
        assert call_subject == "engagement.follow"
        assert call_payload["event_type"] == "follow"
        assert call_payload["user_id"] == str(mock_user_alice.user_id)
        assert call_payload["target_user_id"] == bob_id

        # Duplicate follow is idempotent (no error, no second event)
        dup_follow_res = client.post(f"/v1/social/follow/{bob_id}")
        assert dup_follow_res.status_code == 200
        assert mock_nats_publish.call_count == 1

        # ── 8. Verify Follower count incremented on Bob's profile ─────────────
        bob_profile_res = client.get("/v1/profiles/bob_creator")
        assert bob_profile_res.status_code == 200
        assert bob_profile_res.json()["followers_count"] == 1
        assert bob_profile_res.json()["is_following"] is True  # Alice is looking

        # Verify Following count on Alice's profile
        alice_me_res = client.get("/v1/profiles/me")
        assert alice_me_res.status_code == 200
        assert alice_me_res.json()["following_count"] == 1

        # ── 9. Followers and Following lists ──────────────────────────────────
        followers_list_res = client.get(f"/v1/social/{bob_id}/followers")
        assert followers_list_res.status_code == 200
        followers_data = followers_list_res.json()
        assert followers_data["total"] == 1
        assert followers_data["items"][0]["username"] == "alice_prime"

        # ── 10. Unfollow: Alice unfollows Bob ─────────────────────────────────
        unfollow_res = client.delete(f"/v1/social/follow/{bob_id}")
        assert unfollow_res.status_code == 200
        assert unfollow_res.json()["is_following"] is False

        # Verify Follower count decremented
        bob_after_unfollow = client.get("/v1/profiles/bob_creator")
        assert bob_after_unfollow.status_code == 200
        assert bob_after_unfollow.json()["followers_count"] == 0
        assert bob_after_unfollow.json()["is_following"] is False

    app.dependency_overrides.clear()

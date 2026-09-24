"""
routes.py — All Blipps v1 route handlers.

Endpoints:
  POST /v1/auth/signup      — create account, return JWT (accepts JSON or Form)
  POST /v1/auth/login       — email+password → JWT (accepts JSON or Form)
  POST /v1/uploads          — authenticated multipart upload to B2
  GET  /v1/feed             — public, cursor-paginated blipp feed
  GET  /v1/blipps/{id}      — public, single blipp detail
"""
import asyncio
import io
import mimetypes
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from dotenv import load_dotenv

import bcrypt
import mutagen
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from jose import jwt
from pydantic import BaseModel
from sqlalchemy import select

import storage
from deps import CurrentUser, JWT_ALGORITHM, JWT_SECRET, SessionDep
from models import Blipp, User

load_dotenv()

router = APIRouter()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

ALLOWED_AUDIO_CONTENT_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/x-m4a",
    "audio/wav",
    "audio/x-wav",
    "audio/ogg",
    "audio/aac",
    "audio/flac",
    "audio/webm",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _req_id(request: Request) -> str:
    return request.headers.get("x-request-id", str(uuid.uuid4()))


def _err(code: str, message: str, request_id: str, status: int) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"error": {"code": code, "message": message, "request_id": request_id}},
    )


def _issue_jwt(user_id: uuid.UUID) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode({"sub": str(user_id), "exp": exp}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _audio_duration(data: bytes, filename: str) -> Optional[float]:
    """Best-effort duration extraction via mutagen. Returns None on failure."""
    try:
        f = mutagen.File(io.BytesIO(data), filename=filename)
        if f is not None and f.info is not None:
            return round(float(f.info.length), 2)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    created_at: datetime

    class Config:
        from_attributes = True


class BlippOut(BaseModel):
    id: uuid.UUID
    creator_id: uuid.UUID
    creator_username: str
    title: str
    audio_url: str          # presigned B2 URL
    duration_seconds: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


class FeedPage(BaseModel):
    items: list[BlippOut]
    next_cursor: Optional[str]  # ISO 8601 of last item's created_at, or null


# ---------------------------------------------------------------------------
# Internal: build BlippOut from a DB row + username
# ---------------------------------------------------------------------------

def _blipp_out(blipp: Blipp, creator_username: str) -> BlippOut:
    return BlippOut(
        id=blipp.id,
        creator_id=blipp.creator_id,
        creator_username=creator_username,
        title=blipp.title,
        audio_url=storage.presigned_url(blipp.audio_url),   # B2 key → fresh signed URL
        duration_seconds=blipp.duration_seconds,
        created_at=blipp.created_at,
    )


# ---------------------------------------------------------------------------
# Auth routes (accepts either JSON or Form)
# ---------------------------------------------------------------------------

@router.post("/v1/auth/signup", response_model=TokenOut, status_code=201)
async def signup(
    request: Request,
    session: SessionDep,
    email: Optional[str] = Form(None),
    username: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
):
    rid = _req_id(request)

    ct = request.headers.get("content-type", "")
    if "application/json" in ct:
        try:
            body = await request.json()
            email = body.get("email", email)
            username = body.get("username", username)
            password = body.get("password", password)
        except Exception:
            raise _err("INVALID_JSON", "Failed to parse JSON body", rid, 400)

    if not email or not username or not password:
        raise _err("INVALID_INPUT", "email, username, and password are required", rid, 422)

    username = username.strip()
    email = email.strip().lower()

    if len(username) < 2 or len(username) > 40:
        raise _err("INVALID_INPUT", "username must be between 2 and 40 characters", rid, 422)
    if len(password) < 6:
        raise _err("INVALID_INPUT", "password must be at least 6 characters", rid, 422)
    if "@" not in email or "." not in email:
        raise _err("INVALID_INPUT", "Invalid email address format", rid, 422)

    # Check uniqueness
    existing = (await session.execute(
        select(User).where((User.email == email) | (User.username == username))
    )).scalar_one_or_none()

    if existing:
        if existing.email == email:
            raise _err("EMAIL_TAKEN", "Email already registered", rid, 409)
        raise _err("USERNAME_TAKEN", "Username already taken", rid, 409)

    user = User(
        username=username,
        email=email,
        password_hash=_hash_password(password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return TokenOut(access_token=_issue_jwt(user.id))


@router.post("/v1/auth/login", response_model=TokenOut)
async def login(
    request: Request,
    session: SessionDep,
    email: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
):
    rid = _req_id(request)

    ct = request.headers.get("content-type", "")
    if "application/json" in ct:
        try:
            body = await request.json()
            email = body.get("email", email)
            password = body.get("password", password)
        except Exception:
            raise _err("INVALID_JSON", "Failed to parse JSON body", rid, 400)

    if not email or not password:
        raise _err("INVALID_INPUT", "email and password are required", rid, 422)

    email = email.strip().lower()

    user = (await session.execute(
        select(User).where(User.email == email)
    )).scalar_one_or_none()

    if not user or not _verify_password(password, user.password_hash):
        raise _err("INVALID_CREDENTIALS", "Invalid email or password", rid, 401)

    return TokenOut(access_token=_issue_jwt(user.id))


# ---------------------------------------------------------------------------
# Upload route
# ---------------------------------------------------------------------------

@router.post("/v1/uploads", response_model=BlippOut, status_code=201)
async def upload_blipp(
    request: Request,
    session: SessionDep,
    current_user: CurrentUser,
    title: str = Form(..., min_length=1, max_length=200),
    file: UploadFile = File(...),
):
    rid = _req_id(request)

    # Validate MIME type (check both declared content-type and file extension)
    declared_ct = (file.content_type or "").split(";")[0].strip().lower()
    guessed_ct, _ = mimetypes.guess_type(file.filename or "")
    effective_ct = declared_ct or guessed_ct or ""

    if effective_ct not in ALLOWED_AUDIO_CONTENT_TYPES:
        raise _err(
            "INVALID_FILE_TYPE",
            f"Expected an audio file. Got content-type: '{effective_ct or 'unknown'}'",
            rid,
            415,
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise _err("EMPTY_FILE", "Uploaded file is empty", rid, 400)

    # Derive extension — prefer original filename, fall back to .mp3/.bin
    ext = os.path.splitext(file.filename or "")[1].lower() or ".mp3"
    b2_key = f"blipps/{uuid.uuid4()}{ext}"

    # Duration detection (CPU, no I/O)
    duration = _audio_duration(file_bytes, file.filename or f"audio{ext}")

    # Upload to B2 in a thread executor (boto3 is sync/blocking)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: storage.upload(file_bytes, b2_key, effective_ct or "audio/mpeg"),
    )

    blipp = Blipp(
        creator_id=current_user.id,
        title=title.strip(),
        audio_url=b2_key,
        duration_seconds=duration,
    )
    session.add(blipp)
    await session.commit()
    await session.refresh(blipp)

    return _blipp_out(blipp, current_user.username)


# ---------------------------------------------------------------------------
# Feed route
# ---------------------------------------------------------------------------

@router.get("/v1/feed", response_model=FeedPage)
async def get_feed(
    session: SessionDep,
    cursor: Optional[str] = None,
    limit: int = 20,
):
    limit = min(max(limit, 1), 100)

    stmt = select(Blipp).order_by(Blipp.created_at.desc())

    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "BAD_CURSOR",
                        "message": "cursor must be an ISO 8601 timestamp",
                        "request_id": None,
                    }
                },
            )
        stmt = stmt.where(Blipp.created_at < cursor_dt)

    stmt = stmt.limit(limit)
    blipps = (await session.execute(stmt)).scalars().all()

    # Batch-fetch creator usernames in one query
    creator_ids = list({b.creator_id for b in blipps})
    users_result = await session.execute(
        select(User).where(User.id.in_(creator_ids))
    )
    username_map: dict[uuid.UUID, str] = {
        u.id: u.username for u in users_result.scalars().all()
    }

    items = [_blipp_out(b, username_map.get(b.creator_id, "unknown")) for b in blipps]

    next_cursor: Optional[str] = None
    if len(blipps) == limit:
        last_dt = blipps[-1].created_at
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        next_cursor = last_dt.isoformat()

    return FeedPage(items=items, next_cursor=next_cursor)


# ---------------------------------------------------------------------------
# Single blipp
# ---------------------------------------------------------------------------

@router.get("/v1/blipps/{blipp_id}", response_model=BlippOut)
async def get_blipp(
    blipp_id: uuid.UUID,
    session: SessionDep,
    request: Request,
):
    rid = _req_id(request)
    blipp = await session.get(Blipp, blipp_id)
    if blipp is None:
        raise _err("NOT_FOUND", f"Blipp {blipp_id} not found", rid, 404)

    creator = await session.get(User, blipp.creator_id)
    return _blipp_out(blipp, creator.username if creator else "unknown")

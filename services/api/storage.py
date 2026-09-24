"""
storage.py — Backblaze B2 object storage via the S3-compatible API.

Design choices:
  - boto3 (sync) rather than aioboto3 — simpler, fewer dependencies.
    The upload() function is meant to be called via asyncio.get_event_loop()
    .run_in_executor() from async route handlers.
  - presigned_url() is CPU-only (no network I/O) so it's safe to call
    directly inside async handlers.
  - The B2 bucket is PRIVATE. audio_url in the DB stores the object key
    (e.g. "blipps/<uuid>.mp3"). Every API response generates a fresh
    presigned URL valid for PRESIGN_TTL_SECONDS.
"""
import io
import os
from functools import lru_cache
from dotenv import load_dotenv

import boto3
from botocore.client import Config

load_dotenv()

# ---------------------------------------------------------------------------
# Config (all from env)
# ---------------------------------------------------------------------------
B2_ENDPOINT: str = os.getenv("B2_ENDPOINT", "https://s3.eu-central-003.backblazeb2.com")
B2_REGION: str = os.getenv("B2_REGION", "eu-central-003")
B2_KEY_ID: str = os.getenv("B2_KEY_ID", "")
B2_APP_KEY: str = os.getenv("B2_APP_KEY", "")
B2_BUCKET_NAME: str = os.getenv("B2_BUCKET_NAME", "Blipp-bucket")

PRESIGN_TTL_SECONDS: int = int(os.getenv("PRESIGN_TTL_SECONDS", "3600"))

# Ensure endpoint has scheme
if not B2_ENDPOINT.startswith("http"):
    B2_ENDPOINT = f"https://{B2_ENDPOINT}"


@lru_cache(maxsize=1)
def _client():
    """Lazily create and cache the boto3 S3 client."""
    return boto3.client(
        "s3",
        endpoint_url=B2_ENDPOINT,
        aws_access_key_id=B2_KEY_ID,
        aws_secret_access_key=B2_APP_KEY,
        region_name=B2_REGION,
        config=Config(signature_version="s3v4"),
    )


def upload(file_bytes: bytes, key: str, content_type: str) -> str:
    """
    Upload bytes to B2. Blocking — call from a thread executor.
    Returns the object key (same as input `key`).
    """
    _client().upload_fileobj(
        io.BytesIO(file_bytes),
        B2_BUCKET_NAME,
        key,
        ExtraArgs={"ContentType": content_type},
    )
    return key


def presigned_url(key: str, expires: int = PRESIGN_TTL_SECONDS) -> str:
    """
    Generate a presigned GET URL for a B2 object.
    CPU-only — safe to call directly in async handlers.
    """
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": B2_BUCKET_NAME, "Key": key},
        ExpiresIn=expires,
    )


def ping() -> bool:
    """Quick connectivity check — lists bucket with max 1 key."""
    try:
        _client().list_objects_v2(Bucket=B2_BUCKET_NAME, MaxKeys=1)
        return True
    except Exception:
        return False

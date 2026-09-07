"""
S3/MinIO and local storage adapter for auth service, consuming blipp_common.storage.
"""

from blipp_common.storage import (
    StorageService,
    StorageManager,
)
from app.core.config import settings

storage_service = StorageService(settings=settings)
storage_manager = storage_service


def get_playback_url(storage_key: str) -> str:
    """Convenience module-level accessor for get_playback_url."""
    return storage_service.get_playback_url(storage_key)


__all__ = [
    "StorageService",
    "StorageManager",
    "storage_service",
    "storage_manager",
    "get_playback_url",
]

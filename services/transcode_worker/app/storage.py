"""
S3/MinIO storage manager for transcode worker, consuming blipp_common.storage.
"""

from blipp_common.storage import StorageService, StorageManager
from app.config import settings

storage_service = StorageService(settings=settings)
storage_manager = storage_service

__all__ = [
    "StorageService",
    "StorageManager",
    "storage_service",
    "storage_manager",
]

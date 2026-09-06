import os
import logging
import asyncio
from typing import Optional
from urllib.parse import urlparse
import boto3
from botocore.client import Config

from app.config import settings

logger = logging.getLogger("transcode-worker.storage")


class StorageManager:
    def __init__(self):
        self.raw_bucket = settings.S3_BUCKET_RAW_UPLOADS
        self.variants_bucket = settings.S3_BUCKET_AUDIO_VARIANTS
        self.s3_client = None

        if settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY:
            try:
                kwargs = {
                    "aws_access_key_id": settings.S3_ACCESS_KEY_ID,
                    "aws_secret_access_key": settings.S3_SECRET_ACCESS_KEY,
                    "config": Config(signature_version="s3v4"),
                }
                if settings.S3_ENDPOINT_URL:
                    kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
                if settings.S3_REGION_NAME:
                    kwargs["region_name"] = settings.S3_REGION_NAME
                if hasattr(settings, "S3_USE_SSL"):
                    kwargs["use_ssl"] = settings.S3_USE_SSL
                self.s3_client = boto3.client("s3", **kwargs)
                logger.info(f"Initialized S3 storage manager at {settings.S3_ENDPOINT_URL}")
            except Exception as e:
                logger.error(f"Failed to initialize S3 client: {e}")

    def extract_storage_key(self, key_or_url: str) -> str:
        """Extract relative storage key from full S3 URI or path."""
        if not key_or_url:
            return ""
        if key_or_url.startswith("http://") or key_or_url.startswith("https://") or key_or_url.startswith("s3://"):
            path = urlparse(key_or_url).path.lstrip("/")
            for b in (self.raw_bucket, self.variants_bucket):
                if b and path.startswith(f"{b}/"):
                    return path[len(b) + 1:]
            return path
        return key_or_url.lstrip("/")

    def get_s3_uri(self, storage_key: str, bucket_name: Optional[str] = None) -> str:
        bucket = bucket_name or self.variants_bucket
        safe_key = self.extract_storage_key(storage_key)
        endpoint = settings.S3_ENDPOINT_URL.rstrip("/")
        return f"{endpoint}/{bucket}/{safe_key.lstrip('/')}"

    async def download_file(
        self,
        storage_key: str,
        dest_path: str,
        bucket_name: Optional[str] = None,
    ) -> None:
        bucket = bucket_name or self.raw_bucket
        safe_key = self.extract_storage_key(storage_key)
        await asyncio.to_thread(self._download_sync, safe_key, dest_path, bucket)

    def _download_sync(self, safe_key: str, dest_path: str, bucket: str) -> None:
        if not self.s3_client:
            raise RuntimeError("S3 client not initialized")
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        self.s3_client.download_file(
            Bucket=bucket,
            Key=safe_key,
            Filename=dest_path,
        )

    async def upload_file(
        self,
        file_path: str,
        storage_key: str,
        bucket_name: Optional[str] = None,
        content_type: str = "audio/mp4",
    ) -> str:
        bucket = bucket_name or self.variants_bucket
        safe_key = self.extract_storage_key(storage_key)
        await asyncio.to_thread(self._upload_sync, file_path, safe_key, bucket, content_type)
        return self.get_s3_uri(safe_key, bucket_name=bucket)

    def _upload_sync(self, file_path: str, safe_key: str, bucket: str, content_type: str) -> None:
        if not self.s3_client:
            raise RuntimeError("S3 client not initialized")
        self.s3_client.upload_file(
            Filename=file_path,
            Bucket=bucket,
            Key=safe_key,
            ExtraArgs={"ContentType": content_type},
        )


storage_manager = StorageManager()

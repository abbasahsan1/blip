import os
import uuid
import logging
from pathlib import Path
from typing import BinaryIO, Optional
import boto3
from botocore.client import Config
from app.core.config import settings

logger = logging.getLogger("auth-service.storage")


class StorageService:
    def __init__(self):
        self.s3_client = None
        self.bucket_name = settings.S3_BUCKET_NAME
        self.use_s3 = False

        if settings.S3_BUCKET_NAME and settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY:
            try:
                client_kwargs = {
                    "aws_access_key_id": settings.S3_ACCESS_KEY_ID,
                    "aws_secret_access_key": settings.S3_SECRET_ACCESS_KEY,
                    "config": Config(signature_version="s3v4"),
                }
                if settings.S3_ENDPOINT_URL:
                    client_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
                if settings.S3_REGION_NAME:
                    client_kwargs["region_name"] = settings.S3_REGION_NAME

                self.s3_client = boto3.client("s3", **client_kwargs)
                self.use_s3 = True
                logger.info(f"S3/R2 storage adapter initialized with bucket '{self.bucket_name}'")
            except Exception as e:
                logger.warning(f"Failed to initialize S3 client: {e}. Falling back to local storage.")

        # Ensure local upload directory exists
        self.local_dir = Path(settings.STORAGE_LOCAL_DIR)
        try:
            self.local_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # Fallback to /tmp/uploads if directory permission issues arise
            self.local_dir = Path("/tmp/blipp_uploads")
            self.local_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Local storage fallback initialized at '{self.local_dir}'")

    def save_file(
        self,
        file_obj: BinaryIO,
        original_filename: str,
        content_type: Optional[str] = None
    ) -> str:
        """
        Saves the file to S3/R2 or local filesystem and returns canonical public audio_url.
        """
        ext = os.path.splitext(original_filename)[1].lower()
        if not ext:
            ext = ".mp3"

        unique_key = f"{uuid.uuid4()}{ext}"
        mime = content_type or "audio/mpeg"

        if self.use_s3 and self.s3_client and self.bucket_name:
            try:
                file_obj.seek(0)
                self.s3_client.upload_fileobj(
                    file_obj,
                    self.bucket_name,
                    unique_key,
                    ExtraArgs={"ContentType": mime}
                )
                if settings.S3_PUBLIC_URL:
                    base = settings.S3_PUBLIC_URL.rstrip("/")
                    return f"{base}/{unique_key}"
                if settings.S3_ENDPOINT_URL:
                    base = settings.S3_ENDPOINT_URL.rstrip("/")
                    return f"{base}/{self.bucket_name}/{unique_key}"
                return f"https://{self.bucket_name}.s3.amazonaws.com/{unique_key}"
            except Exception as e:
                logger.error(f"Failed to upload to S3: {e}. Falling back to local disk.")

        # Local storage fallback
        file_obj.seek(0)
        local_path = self.local_dir / unique_key
        with open(local_path, "wb") as f:
            while chunk := file_obj.read(1024 * 1024):
                f.write(chunk)

        base_url = settings.PUBLIC_BASE_URL.rstrip("/")
        return f"{base_url}/v1/blipps/audio/{unique_key}"

    def get_local_path(self, filename: str) -> Optional[Path]:
        """Resolve safe local path for static streaming."""
        # Sanitize filename
        safe_name = os.path.basename(filename)
        candidate = self.local_dir / safe_name
        if candidate.exists() and candidate.is_file():
            return candidate
        return None


storage_service = StorageService()

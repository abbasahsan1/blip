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
        content_type: Optional[str] = None,
        creator_id: Optional[str] = None,
    ) -> str:
        """
        Saves the file to S3/R2 or local filesystem and returns canonical public audio_url.
        """
        ext = os.path.splitext(original_filename)[1].lower()
        if not ext:
            ext = ".mp3"

        if creator_id:
            unique_key = f"{creator_id}/{uuid.uuid4()}{ext}"
        else:
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
                return self.get_playback_url(unique_key)
            except Exception as e:
                logger.error(f"Failed to upload to S3: {e}. Falling back to local disk.")

        # Local storage fallback
        file_obj.seek(0)
        local_path = self.local_dir / unique_key
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            while chunk := file_obj.read(1024 * 1024):
                f.write(chunk)

        base_url = settings.PUBLIC_BASE_URL.rstrip("/")
        return f"{base_url}/v1/blipps/audio/{unique_key}"

    def normalize_mime_type(self, filename: str, mime_type: Optional[str] = None) -> str:
        """
        Normalizes MIME types to prevent S3 signature mismatches across platforms.
        """
        ext = os.path.splitext(filename)[1].lower()
        ext_map = {
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".mp4": "audio/mp4",
            ".aac": "audio/aac",
            ".wav": "audio/wav",
            ".ogg": "audio/ogg",
            ".flac": "audio/flac",
            ".webm": "audio/webm",
        }
        if ext in ext_map:
            return ext_map[ext]
        if mime_type:
            clean = mime_type.lower().split(";")[0].strip()
            if clean in ("audio/mp3", "audio/mpeg3", "audio/x-mpeg-3"):
                return "audio/mpeg"
            if clean in ("audio/x-m4a", "audio/m4a"):
                return "audio/mp4"
            if clean in ("audio/x-wav", "audio/vnd.wave"):
                return "audio/wav"
            if clean.startswith("audio/"):
                return clean
        return "audio/mpeg"

    def extract_storage_key(self, key_or_url: str) -> str:
        """Extract relative storage key from a full URL or storage path."""
        if not key_or_url:
            return ""
        if "/v1/blipps/audio/" in key_or_url:
            return key_or_url.split("/v1/blipps/audio/", 1)[1]
        if key_or_url.startswith("http://") or key_or_url.startswith("https://"):
            from urllib.parse import urlparse
            path = urlparse(key_or_url).path.lstrip("/")
            if self.bucket_name and path.startswith(f"{self.bucket_name}/"):
                return path[len(self.bucket_name) + 1:]
            return path
        return key_or_url.lstrip("/")

    def get_playback_url(self, storage_key: str) -> str:
        """
        Generates presigned download URLs if PUBLIC_STORAGE_BASE_URL is not set to a public CDN.
        Prevents 403 Forbidden on private Backblaze B2/S3 buckets.
        """
        safe_key = self.extract_storage_key(storage_key)
        if not safe_key:
            return storage_key

        cdn_base = settings.PUBLIC_STORAGE_BASE_URL or settings.S3_PUBLIC_URL
        if cdn_base:
            return f"{cdn_base.rstrip('/')}/{safe_key}"
        if self.use_s3 and self.s3_client and self.bucket_name:
            try:
                return self.s3_client.generate_presigned_url(
                    ClientMethod="get_object",
                    Params={"Bucket": self.bucket_name, "Key": safe_key},
                    ExpiresIn=86400,  # 24 hours
                )
            except Exception as e:
                logger.warning(f"Failed to generate presigned playback URL: {e}")
        base_url = settings.PUBLIC_BASE_URL.rstrip("/")
        return f"{base_url}/v1/blipps/audio/{safe_key}"

    def get_public_audio_url(self, storage_key: str) -> str:
        return self.get_playback_url(storage_key)

    def get_local_path(self, filename: str) -> Optional[Path]:
        """Resolve safe local path for static streaming."""
        clean_name = filename.lstrip("/")
        try:
            candidate = (self.local_dir / clean_name).resolve()
            if candidate.is_file() and str(candidate).startswith(str(self.local_dir.resolve())):
                return candidate
        except Exception:
            pass
        safe_name = os.path.basename(filename)
        candidate_flat = self.local_dir / safe_name
        if candidate_flat.exists() and candidate_flat.is_file():
            return candidate_flat
        return None


storage_service = StorageService()


def get_playback_url(storage_key: str) -> str:
    """Convenience module-level accessor for get_playback_url."""
    return storage_service.get_playback_url(storage_key)


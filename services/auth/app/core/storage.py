import os
import uuid
import logging
import asyncio
from pathlib import Path
from typing import BinaryIO, Optional, Union
import boto3
from botocore.client import Config
from app.core.config import settings

logger = logging.getLogger("auth-service.storage")


class StorageService:
    def __init__(self):
        self.bucket_name = settings.S3_BUCKET_NAME or settings.S3_BUCKET_RAW_UPLOADS or "blipp-raw-uploads"
        self.raw_bucket = settings.S3_BUCKET_RAW_UPLOADS or "blipp-raw-uploads"
        self.variants_bucket = settings.S3_BUCKET_AUDIO_VARIANTS or "blipp-audio-variants"
        self.use_s3 = False
        self.s3_client = None

        if settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY:
            try:
                client_kwargs = self._get_client_kwargs()
                self.s3_client = boto3.client("s3", **client_kwargs)
                self.use_s3 = True
                logger.info(f"S3/MinIO storage adapter initialized with default bucket '{self.bucket_name}'")
            except Exception as e:
                logger.warning(f"Failed to initialize S3 client: {e}. Falling back to local storage.")

        # Ensure local upload directory exists as a fallback
        self.local_dir = Path(settings.STORAGE_LOCAL_DIR)
        try:
            self.local_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.local_dir = Path("/tmp/blipp_uploads")
            self.local_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Local storage fallback initialized at '{self.local_dir}'")

    def _get_client_kwargs(self) -> dict:
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
        return kwargs

    async def upload_file(
        self,
        data: Union[bytes, BinaryIO],
        storage_key: str,
        bucket_name: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> str:
        """
        Asynchronously upload bytes or a file stream to S3/MinIO.
        """
        return await asyncio.to_thread(
            self._upload_file_sync, data, storage_key, bucket_name, content_type
        )

    def _upload_file_sync(
        self,
        data: Union[bytes, BinaryIO],
        storage_key: str,
        bucket_name: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> str:
        bucket = bucket_name or self.bucket_name
        mime = content_type or self.normalize_mime_type(storage_key)

        if self.use_s3 and self.s3_client:
            try:
                if isinstance(data, (bytes, bytearray)):
                    self.s3_client.put_object(
                        Bucket=bucket,
                        Key=storage_key,
                        Body=data,
                        ContentType=mime,
                    )
                else:
                    data.seek(0)
                    self.s3_client.upload_fileobj(
                        data,
                        bucket,
                        storage_key,
                        ExtraArgs={"ContentType": mime},
                    )
                return self.get_playback_url(storage_key, bucket_name=bucket)
            except Exception as e:
                logger.error(f"Async S3 upload error: {e}. Falling back to local disk.")

        # Local storage fallback
        local_path = self.local_dir / storage_key.lstrip("/")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            if isinstance(data, (bytes, bytearray)):
                f.write(data)
            else:
                data.seek(0)
                while chunk := data.read(1024 * 1024):
                    f.write(chunk)

        base_url = settings.PUBLIC_BASE_URL.rstrip("/")
        return f"{base_url}/v1/blipps/audio/{storage_key.lstrip('/')}"

    async def download_file(
        self,
        storage_key: str,
        bucket_name: Optional[str] = None,
    ) -> bytes:
        """
        Asynchronously download an object's bytes from S3/MinIO.
        """
        return await asyncio.to_thread(self._download_file_sync, storage_key, bucket_name)

    def _download_file_sync(
        self,
        storage_key: str,
        bucket_name: Optional[str] = None,
    ) -> bytes:
        bucket = bucket_name or self.bucket_name
        safe_key = self.extract_storage_key(storage_key)

        if self.use_s3 and self.s3_client:
            response = self.s3_client.get_object(Bucket=bucket, Key=safe_key)
            return response["Body"].read()

        local_path = self.get_local_path(safe_key)
        if local_path and local_path.is_file():
            with open(local_path, "rb") as f:
                return f.read()

        raise FileNotFoundError(f"Object '{safe_key}' not found in storage")

    async def check_health(self) -> bool:
        """
        Health probe to verify S3/MinIO connectivity and bucket accessibility.
        """
        return await asyncio.to_thread(self._check_health_sync)

    def _check_health_sync(self) -> bool:
        if not self.use_s3 or not self.s3_client:
            return self.local_dir.exists()
        try:
            resp = self.s3_client.list_buckets()
            bucket_names = [b["Name"] for b in resp.get("Buckets", [])]
            logger.debug(f"S3/MinIO health check detected buckets: {bucket_names}")
            return True
        except Exception as e:
            logger.warning(f"S3/MinIO health check failed: {e}")
            return False

    def generate_presigned_put_url(
        self,
        storage_key: str,
        content_type: str = "audio/mpeg",
        bucket_name: Optional[str] = None,
        expires_in: int = 3600,
    ) -> str:
        """
        Generate a presigned PUT URL for direct client upload.
        """
        bucket = bucket_name or self.bucket_name
        if self.use_s3 and self.s3_client:
            return self.s3_client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": bucket,
                    "Key": storage_key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in,
            )
        base_url = settings.PUBLIC_BASE_URL.rstrip("/")
        return f"{base_url}/v1/uploads/direct/{storage_key}"

    def save_file(
        self,
        file_obj: BinaryIO,
        original_filename: str,
        content_type: Optional[str] = None,
        creator_id: Optional[str] = None,
        bucket_name: Optional[str] = None,
    ) -> str:
        """
        Synchronously saves the file to S3/MinIO or local filesystem and returns canonical audio_url.
        """
        ext = os.path.splitext(original_filename)[1].lower() or ".mp3"
        bucket = bucket_name or self.bucket_name

        if creator_id:
            unique_key = f"{creator_id}/{uuid.uuid4()}{ext}"
        else:
            unique_key = f"{uuid.uuid4()}{ext}"
        mime = content_type or self.normalize_mime_type(original_filename)

        if self.use_s3 and self.s3_client:
            try:
                file_obj.seek(0)
                self.s3_client.upload_fileobj(
                    file_obj,
                    bucket,
                    unique_key,
                    ExtraArgs={"ContentType": mime},
                )
                return self.get_playback_url(unique_key, bucket_name=bucket)
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
        """Normalizes MIME types to prevent S3 signature mismatches."""
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
            for b in (self.bucket_name, self.raw_bucket, self.variants_bucket):
                if b and path.startswith(f"{b}/"):
                    return path[len(b) + 1:]
            return path
        return key_or_url.lstrip("/")

    def get_playback_url(
        self,
        storage_key: str,
        bucket_name: Optional[str] = None,
        expires_in: int = 86400,
    ) -> str:
        """
        Generates presigned download URLs or public CDN URLs.
        """
        safe_key = self.extract_storage_key(storage_key)
        if not safe_key:
            return storage_key

        bucket = bucket_name or self.bucket_name
        cdn_base = settings.PUBLIC_STORAGE_BASE_URL or settings.S3_PUBLIC_URL
        if cdn_base:
            return f"{cdn_base.rstrip('/')}/{safe_key}"

        if self.use_s3 and self.s3_client:
            try:
                return self.s3_client.generate_presigned_url(
                    ClientMethod="get_object",
                    Params={"Bucket": bucket, "Key": safe_key},
                    ExpiresIn=expires_in,
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


import os
import uuid
import logging
import asyncio
from pathlib import Path
from typing import BinaryIO, Optional, Union, Any
from urllib.parse import urlparse
import boto3
from botocore.client import Config

from blipp_common.config import BaseCommonSettings

logger = logging.getLogger("blipp_common.storage")


class StorageService:
    """
    Async S3 / MinIO client manager with chunked streaming and presigned URL helpers.
    Includes local filesystem fallback when S3 / MinIO is unreachable.
    """

    def __init__(self, settings: Optional[BaseCommonSettings] = None):
        self.settings = settings or BaseCommonSettings()
        self.bucket_name = (
            self.settings.S3_BUCKET_NAME
            or self.settings.S3_BUCKET_RAW_UPLOADS
            or "blipp-raw-uploads"
        )
        self.raw_bucket = self.settings.S3_BUCKET_RAW_UPLOADS or "blipp-raw-uploads"
        self.variants_bucket = self.settings.S3_BUCKET_AUDIO_VARIANTS or "blipp-audio-variants"
        self.stories_bucket = getattr(self.settings, "S3_BUCKET_STORIES", "blipp-stories") or "blipp-stories"
        self.use_s3 = False
        self.internal_s3_client = None
        self.public_s3_client = None
        self.s3_client = None  # Backwards-compatible alias for internal operations

        if self.settings.S3_ACCESS_KEY_ID and self.settings.S3_SECRET_ACCESS_KEY:
            # 1. Internal S3 client for server-side cluster RPCs
            try:
                internal_kwargs = self._get_client_kwargs(endpoint_url=self.settings.s3_endpoint_url)
                self.internal_s3_client = boto3.client("s3", **internal_kwargs)
                self.s3_client = self.internal_s3_client
                self.use_s3 = True
                logger.info(
                    f"S3/MinIO internal storage adapter initialized with default bucket '{self.bucket_name}' "
                    f"at {self.settings.s3_endpoint_url}"
                )
            except Exception as e:
                logger.warning(f"Failed to initialize internal S3 client: {e}. Falling back to local storage.")

            # 2. Public S3 client for client presigned URLs and public host SigV4 signatures
            try:
                public_kwargs = self._get_client_kwargs(endpoint_url=self.settings.s3_public_endpoint_url)
                self.public_s3_client = boto3.client("s3", **public_kwargs)
                logger.info(
                    f"S3/MinIO public URL generator initialized at {self.settings.s3_public_endpoint_url}"
                )
            except Exception as e:
                logger.warning(f"Failed to initialize public S3 client: {e}")

        # Ensure local upload directory exists as a fallback
        self.local_dir = Path(self.settings.STORAGE_LOCAL_DIR)
        try:
            self.local_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.local_dir = Path("/tmp/blipp_uploads")
            self.local_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Local storage fallback initialized at '{self.local_dir}'")

    def _get_client_kwargs(self, endpoint_url: Optional[str] = None) -> dict:
        kwargs = {
            "aws_access_key_id": self.settings.S3_ACCESS_KEY_ID,
            "aws_secret_access_key": self.settings.S3_SECRET_ACCESS_KEY,
            "config": Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        }
        endpoint = endpoint_url or self.settings.s3_endpoint_url
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        if self.settings.S3_REGION_NAME:
            kwargs["region_name"] = self.settings.S3_REGION_NAME
        if hasattr(self.settings, "S3_USE_SSL"):
            kwargs["use_ssl"] = self.settings.S3_USE_SSL
        return kwargs

    async def upload_file(
        self,
        data: Union[str, Path, bytes, BinaryIO],
        storage_key: str,
        bucket_name: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> str:
        """
        Asynchronously upload file path, bytes, or file stream to S3/MinIO.
        Returns the canonical storage/playback URL or S3 URI.
        """
        return await asyncio.to_thread(
            self._upload_file_sync, data, storage_key, bucket_name, content_type
        )

    def _upload_file_sync(
        self,
        data: Union[str, Path, bytes, BinaryIO],
        storage_key: str,
        bucket_name: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> str:
        bucket = bucket_name or self.bucket_name
        mime = content_type or self.normalize_mime_type(storage_key)
        safe_key = self.extract_storage_key(storage_key)

        # Case 1: data is a filesystem path string or Path object
        if isinstance(data, (str, Path)) and os.path.exists(str(data)):
            file_path = str(data)
            if self.use_s3 and self.s3_client:
                try:
                    self.s3_client.upload_file(
                        Filename=file_path,
                        Bucket=bucket,
                        Key=safe_key,
                        ExtraArgs={"ContentType": mime},
                    )
                    return self.get_s3_uri(safe_key, bucket_name=bucket)
                except Exception as e:
                    logger.error(f"S3 upload_file path error: {e}. Falling back to local disk.")

            # Local copy fallback
            local_path = self.local_dir / safe_key.lstrip("/")
            local_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "rb") as src, open(local_path, "wb") as dst:
                while chunk := src.read(1024 * 1024):
                    dst.write(chunk)
            base_url = self.settings.PUBLIC_BASE_URL.rstrip("/")
            return f"{base_url}/v1/blipps/audio/{safe_key.lstrip('/')}"

        # Case 2: data is in-memory bytes or file-like object
        if self.use_s3 and self.s3_client:
            try:
                if isinstance(data, (bytes, bytearray)):
                    self.s3_client.put_object(
                        Bucket=bucket,
                        Key=safe_key,
                        Body=data,
                        ContentType=mime,
                    )
                else:
                    if hasattr(data, "seek"):
                        data.seek(0)
                    self.s3_client.upload_fileobj(
                        data,
                        bucket,
                        safe_key,
                        ExtraArgs={"ContentType": mime},
                    )
                return self.get_playback_url(safe_key, bucket_name=bucket)
            except Exception as e:
                logger.error(f"Async S3 upload error: {e}. Falling back to local disk.")

        # Local storage fallback
        local_path = self.local_dir / safe_key.lstrip("/")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            if isinstance(data, (bytes, bytearray)):
                f.write(data)
            elif hasattr(data, "read"):
                if hasattr(data, "seek"):
                    data.seek(0)
                while chunk := data.read(1024 * 1024):
                    f.write(chunk)

        base_url = self.settings.PUBLIC_BASE_URL.rstrip("/")
        return f"{base_url}/v1/blipps/audio/{safe_key.lstrip('/')}"

    async def upload_stream(
        self,
        file: Any,
        storage_key: str,
        bucket_name: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> str:
        """
        Streams file chunks asynchronously to S3/MinIO without reading entire file into memory.
        Returns the canonical raw_file_url / s3 URI.
        """
        return await asyncio.to_thread(
            self._upload_stream_sync, file, storage_key, bucket_name, content_type
        )

    def _upload_stream_sync(
        self,
        file: Any,
        storage_key: str,
        bucket_name: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> str:
        bucket = bucket_name or self.raw_bucket
        mime = content_type or self.normalize_mime_type(storage_key)
        safe_key = self.extract_storage_key(storage_key)
        file_obj = getattr(file, "file", file)

        if self.use_s3 and self.s3_client:
            try:
                if hasattr(file_obj, "seek"):
                    file_obj.seek(0)
                self.s3_client.upload_fileobj(
                    file_obj,
                    bucket,
                    safe_key,
                    ExtraArgs={"ContentType": mime},
                )
                return self.get_s3_uri(safe_key, bucket_name=bucket)
            except Exception as e:
                logger.error(f"S3 upload_stream error: {e}. Falling back to local disk.")

        # Local storage fallback
        local_path = self.local_dir / safe_key.lstrip("/")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        with open(local_path, "wb") as f:
            while chunk := file_obj.read(1024 * 1024):
                f.write(chunk)

        base_url = self.settings.PUBLIC_BASE_URL.rstrip("/")
        return f"{base_url}/v1/blipps/audio/{safe_key.lstrip('/')}"

    async def download_file(
        self,
        storage_key: str,
        dest_path: Optional[str] = None,
        bucket_name: Optional[str] = None,
    ) -> Optional[bytes]:
        """
        Asynchronously downloads an object from S3/MinIO.
        - If dest_path is supplied: downloads to file path on disk and returns None.
        - If dest_path is None: reads and returns object content as bytes.
        """
        return await asyncio.to_thread(
            self._download_file_sync, storage_key, dest_path, bucket_name
        )

    def _download_file_sync(
        self,
        storage_key: str,
        dest_path: Optional[str] = None,
        bucket_name: Optional[str] = None,
    ) -> Optional[bytes]:
        bucket = bucket_name or self.bucket_name
        safe_key = self.extract_storage_key(storage_key)

        if dest_path:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            if self.use_s3 and self.s3_client:
                self.s3_client.download_file(
                    Bucket=bucket,
                    Key=safe_key,
                    Filename=dest_path,
                )
                return None
            local_path = self.get_local_path(safe_key)
            if local_path and local_path.is_file():
                with open(local_path, "rb") as src, open(dest_path, "wb") as dst:
                    while chunk := src.read(1024 * 1024):
                        dst.write(chunk)
                return None
            raise FileNotFoundError(f"Object '{safe_key}' not found in storage")

        # Return bytes
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
        client = self.internal_s3_client or self.s3_client
        if not self.use_s3 or not client:
            return self.local_dir.exists()
        try:
            resp = client.list_buckets()
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
        Generate a presigned PUT URL for direct client upload using the public endpoint.
        """
        bucket = bucket_name or self.bucket_name
        safe_key = self.extract_storage_key(storage_key)
        client = self.public_s3_client or self.internal_s3_client or self.s3_client
        if self.use_s3 and client:
            return client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": bucket,
                    "Key": safe_key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in,
            )
        base_url = self.settings.s3_public_endpoint_url.rstrip("/")
        return f"{base_url}/{bucket}/{safe_key}"

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

        base_url = self.settings.PUBLIC_BASE_URL.rstrip("/")
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
        """Extract relative storage key from a full URL, S3 URI, or storage path."""
        if not key_or_url:
            return ""
        clean_url = key_or_url.split("?")[0]
        if "/v1/blipps/audio/" in clean_url:
            return clean_url.split("/v1/blipps/audio/", 1)[1]
        if clean_url.startswith("http://") or clean_url.startswith("https://") or clean_url.startswith("s3://"):
            path = urlparse(clean_url).path.lstrip("/")
            for b in (self.bucket_name, self.raw_bucket, self.variants_bucket, self.stories_bucket):
                if b and path.startswith(f"{b}/"):
                    return path[len(b) + 1:]
            return path
        return clean_url.lstrip("/")

    def get_playback_url(
        self,
        storage_key: str,
        bucket_name: Optional[str] = None,
        expires_in: int = 86400,
    ) -> str:
        """
        Generates presigned download URLs or public CDN URLs targeting the public S3 endpoint.
        """
        safe_key = self.extract_storage_key(storage_key)
        if not safe_key:
            return storage_key

        bucket = bucket_name or self.variants_bucket or self.bucket_name
        cdn_base = self.settings.PUBLIC_STORAGE_BASE_URL or self.settings.S3_PUBLIC_URL
        if cdn_base:
            return f"{cdn_base.rstrip('/')}/{safe_key}"

        client = self.public_s3_client or self.internal_s3_client or self.s3_client
        if self.use_s3 and client:
            try:
                return client.generate_presigned_url(
                    ClientMethod="get_object",
                    Params={"Bucket": bucket, "Key": safe_key},
                    ExpiresIn=expires_in,
                )
            except Exception as e:
                logger.warning(f"Failed to generate presigned playback URL: {e}")

        base_url = self.settings.s3_public_endpoint_url.rstrip("/")
        return f"{base_url}/{bucket}/{safe_key}"

    def get_s3_uri(self, storage_key: str, bucket_name: Optional[str] = None) -> str:
        """
        Generates canonical S3/MinIO URI for an object using the externally reachable public endpoint.
        """
        bucket = bucket_name or self.raw_bucket
        safe_key = self.extract_storage_key(storage_key)
        endpoint = (self.settings.s3_public_endpoint_url or self.settings.s3_endpoint_url).rstrip("/")
        return f"{endpoint}/{bucket}/{safe_key.lstrip('/')}"

    def sanitize_public_url(self, url: str) -> str:
        """Ensures any URL with internal cluster hostnames is rewritten to the public endpoint."""
        if not url:
            return ""
        internal = self.settings.s3_endpoint_url.rstrip("/")
        public = self.settings.s3_public_endpoint_url.rstrip("/")
        if internal and internal in url:
            return url.replace(internal, public)
        for pattern in (
            "http://minio.blipp.svc.cluster.local:9000",
            "http://minio:9000",
        ):
            if pattern in url:
                return url.replace(pattern, public)
        return url

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

    async def delete_file(self, storage_key: str, bucket_name: Optional[str] = None) -> bool:
        """Asynchronously deletes an object from S3/MinIO and/or local filesystem fallback."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._delete_file_sync, storage_key, bucket_name)

    def _delete_file_sync(self, storage_key: str, bucket_name: Optional[str] = None) -> bool:
        """Synchronously deletes an object from S3/MinIO and/or local filesystem."""
        bucket = bucket_name or self.bucket_name
        safe_key = self.extract_storage_key(storage_key)
        deleted = False

        if self.use_s3:
            client = self.internal_s3_client or self.s3_client
            if client:
                try:
                    client.delete_object(Bucket=bucket, Key=safe_key)
                    deleted = True
                    logger.info(f"Deleted object '{safe_key}' from bucket '{bucket}'")
                except Exception as e:
                    logger.warning(f"Failed to delete S3 object {bucket}/{safe_key}: {e}")

        # Local storage fallback removal
        local_path = self.local_dir / safe_key.lstrip("/")
        if local_path.exists() and local_path.is_file():
            try:
                local_path.unlink()
                deleted = True
                logger.info(f"Deleted local file '{local_path}'")
            except Exception as e:
                logger.warning(f"Failed to remove local file {local_path}: {e}")

        return deleted


# Re-export StorageManager alias for backward compatibility across worker services
StorageManager = StorageService

storage_service = StorageService()
storage_manager = storage_service


def get_playback_url(storage_key: str) -> str:
    """Convenience module-level accessor for get_playback_url."""
    return storage_service.get_playback_url(storage_key)

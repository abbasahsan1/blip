from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseCommonSettings(BaseSettings):
    """
    Base configuration settings shared across all Blipp platform services and workers.
    Inherits from pydantic_settings.BaseSettings with environment variable overrides.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ─── PostgreSQL Database ──────────────────────────────────────────────────
    POSTGRES_HOST: str = "postgres.blipp.svc.cluster.local"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "keycloak"
    POSTGRES_PASSWORD: str = "keycloak_secure_db_pass"
    POSTGRES_DB: str = "blipp"

    @field_validator("POSTGRES_PORT", mode="before")
    @classmethod
    def parse_postgres_port(cls, v: Any) -> int:
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            if ":" in v:
                v = v.split(":")[-1]
            try:
                return int(v)
            except ValueError:
                return 5432
        return 5432

    @property
    def async_database_url(self) -> str:
        """SQLAlchemy asynchronous connection string via asyncpg driver."""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def sync_database_url(self) -> str:
        """Standard synchronous PostgreSQL connection string."""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # ─── NATS JetStream Event Bus ─────────────────────────────────────────────
    NATS_URL: str = "nats://nats.blipp.svc.cluster.local:4222"
    NATS_STREAM_UPLOADS: str = "UPLOADS"
    NATS_STREAM_ENGAGEMENT: str = "ENGAGEMENT"
    NATS_SUBJECT_UPLOADS: str = "upload.>"
    NATS_SUBJECT_ENGAGEMENT: str = "engagement.>"
    NATS_CONSUMER_GROUP: str = "blipp-workers"

    # ─── MinIO / S3 Object Storage ────────────────────────────────────────────
    S3_ENDPOINT_URL: str = "http://minio.blipp.svc.cluster.local:9000"
    S3_PUBLIC_ENDPOINT_URL: str = "http://localhost:9000"
    S3_BUCKET_NAME: str = "blipp-raw-uploads"
    S3_BUCKET_RAW_UPLOADS: str = "blipp-raw-uploads"
    S3_BUCKET_AUDIO_VARIANTS: str = "blipp-audio-variants"
    S3_BUCKET_STORIES: str = "blipp-stories"
    MESSAGING_SERVICE_URL: str = "http://messaging-service.blipp.svc.cluster.local:8004"
    SOCIAL_GRAPH_URL: str = "http://social-graph-service.blipp.svc.cluster.local:8003"
    MODERATION_SERVICE_URL: str = "http://moderation-service.blipp.svc.cluster.local:8005"
    S3_ACCESS_KEY_ID: str = "minioadmin"
    S3_SECRET_ACCESS_KEY: str = "minioadmin"
    S3_REGION_NAME: str = "us-east-1"
    S3_USE_SSL: bool = False
    S3_PUBLIC_URL: str = ""
    PUBLIC_STORAGE_BASE_URL: str = ""

    @property
    def s3_endpoint_url(self) -> str:
        """Internal Kubernetes cluster URL for server-side S3 operations."""
        return self.S3_ENDPOINT_URL

    @property
    def s3_public_endpoint_url(self) -> str:
        """Externally reachable S3 URL for client presigned URLs and public media playback."""
        return self.S3_PUBLIC_ENDPOINT_URL or "http://localhost:8419"

    # Local storage fallback directory & public URL
    STORAGE_LOCAL_DIR: str = "/app/data/uploads"
    PUBLIC_BASE_URL: str = "http://100.122.207.32:8419"

    # ─── Redis Cache & Gorse RecSys ───────────────────────────────────────────
    REDIS_URL: str = "redis://redis.blipp.svc.cluster.local:6379/0"
    GORSE_API_URL: str = "http://gorse.blipp.svc.cluster.local:8088"
    GORSE_API_KEY: str = ""

    # ─── App Settings ─────────────────────────────────────────────────────────
    APP_NAME: str = "Blipp Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ─── Keycloak OIDC Authentication ─────────────────────────────────────────
    KEYCLOAK_URL: str = "http://localhost:8419/keycloak"
    KEYCLOAK_INTERNAL_URL: str = "http://keycloak.blipp.svc.cluster.local:8080/keycloak"
    KEYCLOAK_REALM: str = "blipp"
    KEYCLOAK_CLIENT_ID: str = "blipp-app"
    KEYCLOAK_CLIENT_SECRET: str = "blipp-secret-client-token"
    KEYCLOAK_ADMIN: str = "admin"
    JWKS_URL: str = ""

    # ─── Feature Flags & Scheduling ───────────────────────────────────────────
    FEATURE_COPYRIGHT_SCAN_ENABLED: bool = False
    SCHEDULED_PUBLISH_INTERVAL_SECONDS: int = 30

    def get_jwks_url(self) -> str:
        if self.JWKS_URL:
            return self.JWKS_URL
        return f"{self.KEYCLOAK_INTERNAL_URL}/realms/{self.KEYCLOAK_REALM}/protocol/openid-connect/certs"


settings = BaseCommonSettings()


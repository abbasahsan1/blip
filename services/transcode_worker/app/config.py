from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database Settings
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

    # S3 / MinIO Object Storage
    S3_ENDPOINT_URL: str = "http://minio.blipp.svc.cluster.local:9000"
    S3_ACCESS_KEY_ID: str = "minioadmin"
    S3_SECRET_ACCESS_KEY: str = "minioadmin"
    S3_REGION_NAME: str = "us-east-1"
    S3_BUCKET_RAW_UPLOADS: str = "blipp-raw-uploads"
    S3_BUCKET_AUDIO_VARIANTS: str = "blipp-audio-variants"
    S3_USE_SSL: bool = False

    # NATS JetStream Event Bus
    NATS_URL: str = "nats://nats.blipp.svc.cluster.local:4222"
    NATS_STREAM_UPLOADS: str = "UPLOADS"
    NATS_SUBJECT_UPLOADS: str = "upload.>"
    NATS_CONSUMER_GROUP: str = "transcode-workers"


settings = Settings()

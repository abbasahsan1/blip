from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "Blipp Auth Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Keycloak External URL (as accessed by clients / token issuers)
    KEYCLOAK_URL: str = "http://localhost:8419/keycloak"
    
    # Keycloak Internal URL (direct Kubernetes Service DNS)
    KEYCLOAK_INTERNAL_URL: str = "http://keycloak.blipp.svc.cluster.local:8080/keycloak"
    
    KEYCLOAK_REALM: str = "blipp"
    KEYCLOAK_CLIENT_ID: str = "blipp-app"
    KEYCLOAK_CLIENT_SECRET: str = "blipp-secret-client-token"
    KEYCLOAK_ADMIN: str = "admin"
    KEYCLOAK_ADMIN_PASSWORD: str = "admin_master_password"

    # JWKS URL for local signature validation
    JWKS_URL: str = ""

    # PostgreSQL Database
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

    # NATS JetStream Event Bus
    NATS_URL: str = "nats://nats.blipp.svc.cluster.local:4222"
    NATS_STREAM_UPLOADS: str = "UPLOADS"
    NATS_STREAM_ENGAGEMENT: str = "ENGAGEMENT"
    NATS_SUBJECT_UPLOADS: str = "upload.>"
    NATS_SUBJECT_ENGAGEMENT: str = "engagement.>"

    # S3 / MinIO Object Storage
    S3_ENDPOINT_URL: str = "http://minio.blipp.svc.cluster.local:9000"
    S3_BUCKET_NAME: str = "blipp-raw-uploads"
    S3_BUCKET_RAW_UPLOADS: str = "blipp-raw-uploads"
    S3_BUCKET_AUDIO_VARIANTS: str = "blipp-audio-variants"
    S3_ACCESS_KEY_ID: str = "minioadmin"
    S3_SECRET_ACCESS_KEY: str = "minioadmin"
    S3_REGION_NAME: str = "us-east-1"
    S3_USE_SSL: bool = False
    S3_PUBLIC_URL: str = ""
    PUBLIC_STORAGE_BASE_URL: str = ""

    # Local storage fallback directory & public URL
    STORAGE_LOCAL_DIR: str = "/app/data/uploads"
    PUBLIC_BASE_URL: str = "http://100.122.207.32:8419"

    def get_jwks_url(self) -> str:
        if self.JWKS_URL:
            return self.JWKS_URL
        return f"{self.KEYCLOAK_INTERNAL_URL}/realms/{self.KEYCLOAK_REALM}/protocol/openid-connect/certs"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

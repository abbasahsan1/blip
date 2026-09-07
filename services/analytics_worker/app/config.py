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

    # NATS JetStream Event Bus
    NATS_URL: str = "nats://nats.blipp.svc.cluster.local:4222"
    NATS_STREAM_ENGAGEMENT: str = "ENGAGEMENT"
    NATS_SUBJECT_ENGAGEMENT: str = "engagement.>"
    NATS_CONSUMER_GROUP: str = "analytics-workers"


settings = Settings()

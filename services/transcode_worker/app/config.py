from blipp_common.config import BaseCommonSettings


class Settings(BaseCommonSettings):
    """
    Worker-specific settings for the Audio Transcode Worker.
    Inherits all core database, NATS, and S3/MinIO configuration
    from blipp_common.config.BaseCommonSettings.
    """
    NATS_CONSUMER_GROUP: str = "transcode-workers"


settings = Settings()

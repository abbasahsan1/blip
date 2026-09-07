from blipp_common.config import BaseCommonSettings


class Settings(BaseCommonSettings):
    """
    Worker-specific settings for the Analytics Worker.
    Inherits all core database, NATS, Redis, and Gorse configuration
    from blipp_common.config.BaseCommonSettings.
    """
    NATS_CONSUMER_GROUP: str = "analytics-workers"


settings = Settings()

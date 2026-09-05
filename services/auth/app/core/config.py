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

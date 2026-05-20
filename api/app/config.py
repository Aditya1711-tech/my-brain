from pydantic import PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration — validated at boot. Raises if anything missing."""

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase
    next_public_supabase_url: str
    next_public_supabase_anon_key: str
    supabase_service_role_key: SecretStr

    # Database
    database_url: str  # postgresql+asyncpg://...
    redis_url: str

    # Inter-service auth
    backend_api_key: SecretStr

    # LLM
    anthropic_api_key: SecretStr
    openai_api_key: SecretStr

    # Storage
    supabase_storage_bucket: str = "user-uploads"

    # Tracing
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3001"

    # App
    app_env: str = "development"
    app_frontend_url: str = "http://localhost:3000"
    app_api_url: str = "http://localhost:8000"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()

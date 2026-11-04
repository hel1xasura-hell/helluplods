from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://hell:hell@localhost:5432/hell_uploads"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:5173"
    token_encryption_key: str = ""

    owner_email: str = ""
    firebase_project_id: str = ""
    firebase_credentials: str = ""

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    local_storage_dir: str = "./storage"

    piper_binary: str = ""  # path to the free, offline Piper TTS binary
    piper_model: str = ""  # path to a Piper .onnx voice model
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""

    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_redirect_uri: str = ""
    youtube_daily_quota: int = 10000  # raise after Google approves a quota extension
    youtube_upload_cost: int = 1600  # quota units per videos.insert; confirm in your Cloud Console quota page
    frontend_url: str = ""  # where the OAuth callback sends the browser; defaults to the first CORS origin

    rate_limit_per_minute: int = 120
    job_backend: str = "inprocess"  # "inprocess" (FastAPI background task) or "celery"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def frontend_base(self) -> str:
        return (self.frontend_url or (self.cors_origin_list[0] if self.cors_origin_list else "")).rstrip("/")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

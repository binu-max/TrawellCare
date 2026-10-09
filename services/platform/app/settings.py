from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=False)


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://integration_user:integration@localhost:5432/trawellcare"
    platform_service_api_key: str = "local-dev-platform-key"
    integration_base_url: str = "http://127.0.0.1:8004"
    integration_api_key: str = "local-dev-integration-key"
    otp_delivery: str = "integration"
    otp_pepper: str = "local-otp-pepper"
    staff_seed_password: str = "change-me-now"
    staff_totp_secret: str = "JBSWY3DPEHPK3PXP"
    jwt_private_key: str = ""
    jwt_public_key: str = ""
    access_token_minutes: int = 15
    customer_refresh_days: int = 30
    staff_refresh_hours: int = 8
    worker_interval_seconds: float = 30.0

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_settings() -> Settings:
    return Settings()

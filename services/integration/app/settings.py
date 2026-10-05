from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=False)


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://integration_user:integration@localhost:5432/trawellcare"
    integration_api_key: str = "local-dev-integration-key"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False
    sendgrid_api_key: str = ""
    email_from: str = "noreply@localhost"
    worker_interval_seconds: float = 2.0

    @property
    def smtp_login_password(self) -> str:
        return self.smtp_password or self.sendgrid_api_key

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_settings() -> Settings:
    return Settings()

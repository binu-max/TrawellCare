from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=False)


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://integration_user:integration@localhost:5432/trawellcare"
    vault_service_api_key: str = "local-dev-vault-key"
    jwt_public_key: str = ""
    platform_base_url: str = "http://127.0.0.1:8001"
    vault_public_base_url: str = "http://127.0.0.1:8003"
    vault_storage_root: Path = Path("/tmp/trawellcare-vault")
    vault_max_upload_bytes: int = 20 * 1024 * 1024
    upload_token_ttl_seconds: int = 3600
    download_url_ttl_seconds: int = 600
    platform_case_check_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_settings() -> Settings:
    return Settings()

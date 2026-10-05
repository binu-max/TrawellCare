import os
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.main import create_app
from app.settings import Settings

ROOT = Path(__file__).resolve().parents[3]
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://integration_user:integration@localhost:5432/trawellcare_test",
)


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key, value)


_load_dotenv()


@pytest.fixture(scope="session")
def migrated():
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")


@pytest.fixture
async def api(migrated):
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                TRUNCATE
                    integration.travel_calls,
                    integration.travel_options,
                    integration.travel_requests,
                    integration.notification_messages,
                    integration.idempotency_keys,
                    integration.vendor_tokens,
                    integration.outbox,
                    integration.inbox,
                    integration.event_failures,
                    integration.notification_templates,
                    integration.notification_providers,
                    integration.vendors
                RESTART IDENTITY CASCADE
                """
            )
        )
    await engine.dispose()
    settings = Settings(
        database_url=TEST_DATABASE_URL,
        integration_api_key="test-key",
        smtp_host="localhost",
        smtp_port=1025,
        email_from="noreply@localhost",
    )
    application = create_app(settings)
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers["X-Api-Key"] = "test-key"
            yield client, application


def auth_headers(**extra) -> dict:
    return {"X-Api-Key": "test-key", **extra}

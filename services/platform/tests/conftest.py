import os
from pathlib import Path

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
                DO $$ DECLARE r RECORD;
                BEGIN
                  FOR r IN (
                    SELECT tablename FROM pg_tables
                    WHERE schemaname = 'platform' AND tablename <> 'alembic_version_platform'
                  ) LOOP
                    EXECUTE 'TRUNCATE TABLE platform.' || quote_ident(r.tablename) || ' CASCADE';
                  END LOOP;
                END $$;
                """
            )
        )
    await engine.dispose()
    settings = Settings(
        database_url=TEST_DATABASE_URL,
        platform_service_api_key="test-platform-key",
        integration_api_key="test-key",
        otp_delivery="log",
        otp_pepper="test-pepper",
        staff_seed_password="staff-secret",
        staff_totp_secret="JBSWY3DPEHPK3PXP",
    )
    application = create_app(settings)
    async with LifespanManager(application):
        transport_client = __import__("httpx").ASGITransport(app=application)
        async with __import__("httpx").AsyncClient(transport=transport_client, base_url="http://test") as client:
            yield client

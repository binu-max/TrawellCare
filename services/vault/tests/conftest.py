import os
import sys
import uuid
from pathlib import Path

_VAULT_ROOT = Path(__file__).resolve().parents[1]
if str(_VAULT_ROOT) not in sys.path:
    sys.path.insert(0, str(_VAULT_ROOT))

import httpx
import jwt
import pytest
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.main import create_app
from app.settings import Settings

ROOT = Path(__file__).resolve().parents[3]
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://integration_user:integration@localhost:5432/trawellcare_test",
)


def _keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private, public


PRIVATE_KEY, PUBLIC_KEY = _keypair()
CUSTOMER_ID = uuid.uuid4()


def customer_token(customer_id: uuid.UUID | None = None) -> str:
    payload = {
        "sub": str(uuid.uuid4()),
        "kind": "customer",
        "roles": [],
        "customerId": str(customer_id or CUSTOMER_ID),
    }
    return jwt.encode(payload, PRIVATE_KEY, algorithm="RS256")


def finance_token() -> str:
    payload = {
        "sub": str(uuid.uuid4()),
        "kind": "staff",
        "roles": ["finance_maker"],
    }
    return jwt.encode(payload, PRIVATE_KEY, algorithm="RS256")


@pytest.fixture(scope="session")
def migrated():
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    config = Config(str(_VAULT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_VAULT_ROOT / "alembic"))
    os.chdir(_VAULT_ROOT)
    command.upgrade(config, "head")


@pytest.fixture
async def api(migrated, tmp_path):
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                TRUNCATE
                    vault.document_access_log,
                    vault.documents,
                    vault.idempotency_keys,
                    vault.outbox,
                    vault.inbox,
                    vault.event_failures
                RESTART IDENTITY CASCADE
                """
            )
        )
    await engine.dispose()

    settings = Settings(
        database_url=TEST_DATABASE_URL,
        vault_service_api_key="vault-test-key",
        jwt_public_key=PUBLIC_KEY,
        vault_public_base_url="http://test",
        vault_storage_root=tmp_path / "vault",
        platform_case_check_enabled=False,
    )
    application = create_app(settings)
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, application


def auth_headers(token: str, **extra) -> dict:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4()), **extra}

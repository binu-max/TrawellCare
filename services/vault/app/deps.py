from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tc_common import Unauthenticated, ValidationFailed
from tc_common.jwt import TokenActor, actor_from_bearer_token

from app.settings import Settings
from app.storage.local import LocalFilesystemStorage


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


async def get_session(request: Request):
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_http(request: Request):
    return request.app.state.http


def get_storage(request: Request) -> LocalFilesystemStorage:
    return request.app.state.storage


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthenticated("Missing token")
    return authorization.split(" ", 1)[1]


def require_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> TokenActor:
    public_key = request.app.state.jwt_public_key
    if not public_key:
        raise Unauthenticated("JWT public key is not configured")
    return actor_from_bearer_token(_bearer(authorization), public_key)


def require_key(idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> str:
    if not idempotency_key:
        raise ValidationFailed("Idempotency-Key is required")
    return idempotency_key


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def authorization_header(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization:
        raise Unauthenticated("Missing token")
    return authorization


SessionDep = Annotated[AsyncSession, Depends(get_session)]
UserDep = Annotated[TokenActor, Depends(require_user)]
KeyDep = Annotated[str, Depends(require_key)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
StorageDep = Annotated[LocalFilesystemStorage, Depends(get_storage)]
AuthHeaderDep = Annotated[str, Depends(authorization_header)]

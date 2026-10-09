import secrets
from typing import Annotated

import httpx
from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tc_common import Unauthenticated, ValidationFailed

from app.actor import SYSTEM_USER_ID, Actor, clear_actor, set_actor
from app.security import actor_from_token
from app.settings import Settings


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


async def get_session(request: Request):
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            clear_actor()


def get_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthenticated("Missing token")
    return authorization.split(" ", 1)[1]


def require_customer(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Actor:
    actor = actor_from_token(_bearer(authorization), request.app.state.public_key)
    if actor.kind != "customer":
        raise Unauthenticated("Customer token required")
    set_actor(actor)
    return actor


def require_staff(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Actor:
    actor = actor_from_token(_bearer(authorization), request.app.state.public_key)
    if actor.kind != "staff":
        raise Unauthenticated("Staff token required")
    set_actor(actor)
    return actor


def require_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Actor:
    actor = actor_from_token(_bearer(authorization), request.app.state.public_key)
    if actor.kind not in ("customer", "staff"):
        raise Unauthenticated("Invalid token")
    set_actor(actor)
    return actor


def optional_customer(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Actor | None:
    if not authorization:
        return None
    actor = actor_from_token(_bearer(authorization), request.app.state.public_key)
    set_actor(actor)
    return actor


def require_service(
    request: Request,
    x_api_key: Annotated[str | None, Header(alias="X-Api-Key")] = None,
) -> Actor:
    expected = request.app.state.settings.platform_service_api_key
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise Unauthenticated("Invalid API key")
    actor = Actor(id=SYSTEM_USER_ID, kind="service", roles=["service"])
    set_actor(actor)
    return actor


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


SessionDep = Annotated[AsyncSession, Depends(get_session)]
CustomerDep = Annotated[Actor, Depends(require_customer)]
StaffDep = Annotated[Actor, Depends(require_staff)]
UserDep = Annotated[Actor, Depends(require_user)]
ServiceDep = Annotated[Actor, Depends(require_service)]
KeyDep = Annotated[str, Depends(require_key)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]

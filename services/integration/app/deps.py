import secrets

import httpx
from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tc_common import Unauthenticated

from app.settings import Settings


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
) -> None:
    expected = request.app.state.settings.integration_api_key
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise Unauthenticated("Invalid API key")


async def get_session(request: Request):
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.session_factory


def get_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.http

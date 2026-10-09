from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def build_database(database_url: str) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url, pool_size=5, max_overflow=5)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


async def ping(session: AsyncSession) -> None:
    await session.execute(text("SELECT 1"))

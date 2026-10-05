import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.notify.repository import NotifyRepository
from app.modules.notify.service import NotifyService
from app.modules.travel.repository import TravelRepository
from app.modules.travel.service import TravelService
from app.modules.vendors.repository import VendorRepository
from app.modules.vendors.service import VendorService
from app.settings import Settings


async def process_once(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    http: httpx.AsyncClient,
) -> None:
    async with session_factory() as session:
        try:
            await NotifyService(NotifyRepository(session), settings).deliver_due()
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    async with session_factory() as session:
        try:
            service = TravelService(
                TravelRepository(session),
                VendorService(VendorRepository(session)),
                http=http,
                session_factory=session_factory,
            )
            await service.poll_confirmations()
            await session.commit()
        except Exception:
            await session.rollback()
            raise

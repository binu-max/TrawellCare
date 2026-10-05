import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tc_common import RuleFailed

from app.modules.travel.adapters.benzy_flight import BenzyFlightAdapter
from app.modules.travel.adapters.manual import ManualTravelAdapter
from app.modules.travel.adapters.types import TravelPort
from app.modules.vendors.models import Vendor


def build_travel_adapter(
    vendor: Vendor,
    *,
    http: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
) -> TravelPort:
    if vendor.adapter_type == "manual":
        return ManualTravelAdapter()
    if vendor.adapter_type == "benzy_flight":
        return BenzyFlightAdapter(
            vendor=vendor,
            http=http,
            session_factory=session_factory,
            session=session,
        )
    raise RuleFailed(
        f"Adapter {vendor.adapter_type} is not configured",
        code="VENDOR_NOT_CONFIGURED",
    )

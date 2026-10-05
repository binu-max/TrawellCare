from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.vendors.models import Vendor, VendorToken


class VendorRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self) -> list[Vendor]:
        result = await self.session.scalars(select(Vendor).order_by(Vendor.code))
        return list(result)

    async def get(self, code: str) -> Vendor | None:
        return await self.session.scalar(select(Vendor).where(Vendor.code == code))

    async def list_enabled(self, product: str, *, exclude_manual: bool) -> list[Vendor]:
        stmt = select(Vendor).where(Vendor.product == product, Vendor.enabled.is_(True))
        if exclude_manual:
            stmt = stmt.where(Vendor.adapter_type != "manual")
        result = await self.session.scalars(stmt.order_by(Vendor.code))
        return list(result)

    async def get_token(self, vendor_code: str) -> VendorToken | None:
        return await self.session.get(VendorToken, vendor_code)

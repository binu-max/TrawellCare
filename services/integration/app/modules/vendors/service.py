from tc_common import NotFound, RuleFailed

from app.modules.vendors.models import Vendor
from app.modules.vendors.repository import VendorRepository
from app.modules.vendors.schemas import VendorList, VendorUpdate, VendorView


def vendor_view(vendor: Vendor) -> VendorView:
    return VendorView(
        code=vendor.code,
        display_name=vendor.display_name,
        adapter_type=vendor.adapter_type,
        product=vendor.product,
        enabled=vendor.enabled,
        config=vendor.config or {},
    )


class VendorService:
    def __init__(self, repo: VendorRepository):
        self.repo = repo

    async def list_vendors(self) -> VendorList:
        vendors = await self.repo.list_all()
        return VendorList(vendors=[vendor_view(vendor) for vendor in vendors])

    async def set_enabled(self, code: str, body: VendorUpdate) -> VendorView:
        vendor = await self.repo.get(code)
        if vendor is None:
            raise NotFound(f"Unknown vendor {code}")
        vendor.enabled = body.enabled
        await self.repo.session.flush()
        return vendor_view(vendor)

    async def require(self, code: str) -> Vendor:
        vendor = await self.repo.get(code)
        if vendor is None:
            raise NotFound(f"Unknown vendor {code}")
        if not vendor.enabled:
            raise RuleFailed(f"Vendor {code} is disabled", code="VENDOR_DISABLED")
        return vendor

    async def resolve(self, vendor_code: str | None, product: str) -> Vendor:
        if vendor_code:
            return await self.require(vendor_code)
        enabled = await self.repo.list_enabled(product, exclude_manual=True)
        if len(enabled) == 1:
            return enabled[0]
        if not enabled:
            raise RuleFailed(
                f"No enabled {product} vendor. Pass vendorCode or enable one.",
                code="VENDOR_REQUIRED",
            )
        names = ", ".join(vendor.code for vendor in enabled)
        raise RuleFailed(f"Pass vendorCode. Enabled vendors: {names}", code="VENDOR_REQUIRED")

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_api_key
from app.modules.vendors.repository import VendorRepository
from app.modules.vendors.schemas import VendorList, VendorUpdate, VendorView
from app.modules.vendors.service import VendorService

router = APIRouter(prefix="/v1/vendors", tags=["vendors"], dependencies=[Depends(require_api_key)])


def get_vendor_service(session: AsyncSession = Depends(get_session)) -> VendorService:
    return VendorService(VendorRepository(session))


@router.get("", response_model=VendorList)
async def list_vendors(service: VendorService = Depends(get_vendor_service)) -> VendorList:
    return await service.list_vendors()


@router.patch("/{code}", response_model=VendorView)
async def update_vendor(
    code: str,
    body: VendorUpdate,
    service: VendorService = Depends(get_vendor_service),
) -> VendorView:
    return await service.set_enabled(code, body)

from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from tc_common import ValidationFailed

from app.deps import get_http, get_session, get_session_factory, require_api_key
from app.modules.travel.repository import TravelRepository
from app.modules.travel.schemas import (
    CancelBody,
    ConfirmBody,
    CreateTravelRequest,
    ManualOptionBody,
    OptionList,
    OptionView,
    PriceBody,
    SearchCriteria,
    TravelRequestView,
)
from app.modules.travel.service import TravelService
from app.modules.vendors.repository import VendorRepository
from app.modules.vendors.service import VendorService

router = APIRouter(tags=["travel"], dependencies=[Depends(require_api_key)])


def get_travel_service(
    session: AsyncSession = Depends(get_session),
    http=Depends(get_http),
    session_factory=Depends(get_session_factory),
) -> TravelService:
    return TravelService(
        TravelRepository(session),
        VendorService(VendorRepository(session)),
        http=http,
        session_factory=session_factory,
    )


@router.post("/v1/cases/{case_id}/travel-requests", response_model=TravelRequestView, status_code=201)
async def create_travel_request(
    case_id: UUID,
    body: CreateTravelRequest,
    service: TravelService = Depends(get_travel_service),
) -> TravelRequestView:
    return await service.create(case_id, body)


@router.get("/v1/travel-requests/{request_id}", response_model=TravelRequestView)
async def get_travel_request(
    request_id: UUID,
    service: TravelService = Depends(get_travel_service),
) -> TravelRequestView:
    return await service.get(request_id)


@router.get("/v1/travel-requests/{request_id}/options", response_model=OptionList)
async def list_options(
    request_id: UUID,
    service: TravelService = Depends(get_travel_service),
) -> OptionList:
    return await service.list_options(request_id)


@router.post("/v1/travel-requests/{request_id}/search", response_model=OptionList)
async def search_travel(
    request_id: UUID,
    body: SearchCriteria | None = Body(default=None),
    service: TravelService = Depends(get_travel_service),
) -> OptionList:
    return await service.search(request_id, body)


@router.post("/v1/travel-requests/{request_id}/options", response_model=OptionView, status_code=201)
async def add_option(
    request_id: UUID,
    body: ManualOptionBody,
    service: TravelService = Depends(get_travel_service),
) -> OptionView:
    return await service.add_option(request_id, body)


@router.post("/v1/travel-requests/{request_id}/price", response_model=TravelRequestView)
async def price_travel(
    request_id: UUID,
    body: PriceBody,
    service: TravelService = Depends(get_travel_service),
) -> TravelRequestView:
    return await service.price(request_id, body)


@router.post("/v1/travel-requests/{request_id}/confirm", response_model=TravelRequestView)
async def confirm_travel(
    request_id: UUID,
    body: ConfirmBody,
    service: TravelService = Depends(get_travel_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        raise ValidationFailed("Idempotency-Key header is required")
    result = await service.confirm(request_id, body, idempotency_key=idempotency_key)
    if isinstance(result, dict):
        return JSONResponse(status_code=200, content=result)
    return result


@router.post("/v1/travel-requests/{request_id}/cancel", response_model=TravelRequestView)
async def cancel_travel(
    request_id: UUID,
    body: CancelBody,
    service: TravelService = Depends(get_travel_service),
) -> TravelRequestView:
    return await service.cancel(request_id, body)

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from tc_common import ValidationFailed

from app.deps import get_session, get_settings_dep, require_api_key
from app.modules.notify.repository import NotifyRepository
from app.modules.notify.schemas import (
    NotificationView,
    ProviderList,
    ProviderUpdate,
    ProviderView,
    SendNotification,
    SendOtp,
    TemplateUpdate,
    TemplateView,
)
from app.modules.notify.service import NotifyService

router = APIRouter(tags=["notifications"], dependencies=[Depends(require_api_key)])


def get_notify_service(
    session: AsyncSession = Depends(get_session),
    settings=Depends(get_settings_dep),
) -> NotifyService:
    return NotifyService(NotifyRepository(session), settings)


def _require_key(idempotency_key: str | None) -> str:
    if not idempotency_key:
        raise ValidationFailed("Idempotency-Key header is required")
    return idempotency_key


@router.get("/v1/notification-providers", response_model=ProviderList)
async def list_providers(service: NotifyService = Depends(get_notify_service)) -> ProviderList:
    return await service.list_providers()


@router.patch("/v1/notification-providers/{code}", response_model=ProviderView)
async def update_provider(
    code: str,
    body: ProviderUpdate,
    service: NotifyService = Depends(get_notify_service),
) -> ProviderView:
    return await service.set_enabled(code, body)


@router.get("/v1/notification-templates/{key}", response_model=TemplateView)
async def get_template(
    key: str,
    channel: str = Query(...),
    locale: str = Query("en"),
    service: NotifyService = Depends(get_notify_service),
) -> TemplateView:
    return await service.get_template(key, channel, locale)


@router.put("/v1/notification-templates/{key}", response_model=TemplateView)
async def put_template(
    key: str,
    body: TemplateUpdate,
    service: NotifyService = Depends(get_notify_service),
) -> TemplateView:
    return await service.put_template(key, body)


@router.post("/v1/notifications", response_model=NotificationView, status_code=202)
async def send_notification(
    body: SendNotification,
    service: NotifyService = Depends(get_notify_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    result = await service.enqueue(body, idempotency_key=_require_key(idempotency_key))
    if isinstance(result, dict):
        return JSONResponse(status_code=202, content=result)
    return result


@router.post("/v1/sms/otp", status_code=202)
async def send_otp(
    body: SendOtp,
    service: NotifyService = Depends(get_notify_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    return await service.send_otp(body, idempotency_key=_require_key(idempotency_key))


@router.get("/v1/notifications/{message_id}", response_model=NotificationView)
async def get_notification(
    message_id: UUID,
    service: NotifyService = Depends(get_notify_service),
) -> NotificationView:
    return await service.get_message(message_id)


@router.post("/v1/notifications/{message_id}/retry", response_model=NotificationView)
async def retry_notification(
    message_id: UUID,
    service: NotifyService = Depends(get_notify_service),
) -> NotificationView:
    return await service.retry(message_id)


@router.post("/v1/notifications/test-hello", response_model=NotificationView, status_code=202)
async def send_test_hello(
    to: str = Query(..., description="Recipient email"),
    service: NotifyService = Depends(get_notify_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Enqueue a plain **hello world** email (template `test.hello`). Run the worker or use Mailpit."""
    key = idempotency_key or f"test-hello-{to}"
    result = await service.enqueue(
        SendNotification(channel="email", template_key="test.hello", to=to, variables={}),
        idempotency_key=key,
    )
    if isinstance(result, dict):
        return JSONResponse(status_code=202, content=result)
    return result

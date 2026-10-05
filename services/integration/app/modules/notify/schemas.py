from datetime import datetime
from uuid import UUID

from app.api_models import APIModel


class ProviderView(APIModel):
    code: str
    channel: str
    adapter_type: str
    display_name: str
    enabled: bool


class ProviderList(APIModel):
    providers: list[ProviderView]


class ProviderUpdate(APIModel):
    enabled: bool


class TemplateView(APIModel):
    key: str
    channel: str
    locale: str
    subject: str | None
    body: str


class TemplateUpdate(APIModel):
    channel: str
    locale: str = "en"
    subject: str | None = None
    body: str


class SendNotification(APIModel):
    channel: str
    template_key: str
    to: str
    locale: str = "en"
    variables: dict = {}
    provider_code: str | None = None


class SendOtp(APIModel):
    phone_e164: str
    code: str
    locale: str = "en"
    provider_code: str | None = None


class NotificationView(APIModel):
    id: UUID
    template_key: str
    channel: str
    provider_code: str
    to: str
    subject: str | None
    body: str
    status: str
    attempts: int
    last_error: str | None
    created_at: datetime

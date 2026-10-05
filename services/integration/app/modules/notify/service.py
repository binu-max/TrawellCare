import uuid

from tc_common import NotFound, RuleFailed

from app.backoff import MAX_ATTEMPTS, next_attempt_at
from app.idempotency import complete, reserve
from app.modules.notify.adapters import build_sender
from app.modules.notify.models import NotificationMessage, NotificationProvider, NotificationTemplate
from app.modules.notify.render import render
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
from app.settings import Settings


def provider_view(row: NotificationProvider) -> ProviderView:
    return ProviderView(
        code=row.code,
        channel=row.channel,
        adapter_type=row.adapter_type,
        display_name=row.display_name,
        enabled=row.enabled,
    )


def template_view(row: NotificationTemplate) -> TemplateView:
    return TemplateView(key=row.key, channel=row.channel, locale=row.locale, subject=row.subject, body=row.body)


def message_view(row: NotificationMessage) -> NotificationView:
    return NotificationView(
        id=row.id,
        template_key=row.template_key,
        channel=row.channel,
        provider_code=row.provider_code,
        to=row.to_address,
        subject=row.subject,
        body=row.body,
        status=row.status,
        attempts=row.attempts,
        last_error=row.last_error,
        created_at=row.created_at,
    )


class NotifyService:
    def __init__(self, repo: NotifyRepository, settings: Settings):
        self.repo = repo
        self.settings = settings

    async def list_providers(self) -> ProviderList:
        rows = await self.repo.list_providers()
        return ProviderList(providers=[provider_view(row) for row in rows])

    async def set_enabled(self, code: str, body: ProviderUpdate) -> ProviderView:
        row = await self.repo.get_provider(code)
        if row is None:
            raise NotFound(f"Unknown notification provider {code}")
        row.enabled = body.enabled
        await self.repo.session.flush()
        return provider_view(row)

    async def get_template(self, key: str, channel: str, locale: str) -> TemplateView:
        row = await self._template(key, channel, locale)
        return template_view(row)

    async def put_template(self, key: str, body: TemplateUpdate) -> TemplateView:
        row = await self.repo.get_template(key, body.channel, body.locale)
        if row is None:
            row = NotificationTemplate(
                key=key,
                channel=body.channel,
                locale=body.locale,
                subject=body.subject,
                body=body.body,
            )
            self.repo.session.add(row)
        else:
            row.subject = body.subject
            row.body = body.body
        await self.repo.session.flush()
        return template_view(row)

    async def enqueue(self, body: SendNotification, *, idempotency_key: str) -> NotificationView | dict:
        payload = body.model_dump(mode="json", by_alias=True)
        replay = await reserve(self.repo.session, idempotency_key, payload)
        if replay is not None:
            return replay
        message = await self._enqueue(
            channel=body.channel,
            template_key=body.template_key,
            locale=body.locale,
            to=body.to,
            variables=body.variables,
            provider_code=body.provider_code,
            idempotency_key=idempotency_key,
        )
        view = message_view(message)
        await complete(self.repo.session, idempotency_key, 202, view.model_dump(mode="json", by_alias=True))
        return view

    async def send_otp(self, body: SendOtp, *, idempotency_key: str) -> dict:
        payload = {
            "phoneE164": body.phone_e164,
            "locale": body.locale,
            "providerCode": body.provider_code,
            "code": body.code,
        }
        replay = await reserve(self.repo.session, idempotency_key, payload)
        if replay is not None:
            return {"notificationId": replay["id"], "status": replay["status"]}
        message = await self._enqueue(
            channel="sms",
            template_key="otp.sms",
            locale=body.locale,
            to=body.phone_e164,
            variables={"code": body.code},
            provider_code=body.provider_code,
            idempotency_key=idempotency_key,
        )
        view = message_view(message)
        await complete(self.repo.session, idempotency_key, 202, view.model_dump(mode="json", by_alias=True))
        return {"notificationId": str(message.id), "status": message.status}

    async def get_message(self, message_id: uuid.UUID) -> NotificationView:
        row = await self.repo.get_message(message_id)
        if row is None:
            raise NotFound("Notification not found")
        return message_view(row)

    async def retry(self, message_id: uuid.UUID) -> NotificationView:
        row = await self.repo.get_message(message_id)
        if row is None:
            raise NotFound("Notification not found")
        row.status = "pending"
        row.next_attempt_at = None
        row.last_error = None
        await self.repo.session.flush()
        return message_view(row)

    async def deliver_due(self) -> int:
        rows = await self.repo.due_messages()
        for row in rows:
            provider = await self.repo.get_provider(row.provider_code)
            if provider is None or not provider.enabled:
                row.status = "failed"
                row.last_error = "Provider is disabled"
                row.attempts += 1
                if row.attempts >= MAX_ATTEMPTS:
                    row.status = "dead"
                else:
                    row.next_attempt_at = next_attempt_at(row.attempts)
                continue
            try:
                sender = build_sender(provider, self.settings)
                if row.channel == "email":
                    await sender.send(to=row.to_address, subject=row.subject or "", body=row.body)
                else:
                    await sender.send(to=row.to_address, body=row.body)
            except Exception as exc:
                row.attempts += 1
                row.last_error = str(exc)[:500]
                if row.attempts >= MAX_ATTEMPTS:
                    row.status = "dead"
                else:
                    row.status = "failed"
                    row.next_attempt_at = next_attempt_at(row.attempts)
                continue
            row.status = "sent"
            row.last_error = None
        await self.repo.session.flush()
        return len(rows)

    async def _enqueue(
        self,
        *,
        channel: str,
        template_key: str,
        locale: str,
        to: str,
        variables: dict,
        provider_code: str | None,
        idempotency_key: str,
    ) -> NotificationMessage:
        template = await self._template(template_key, channel, locale)
        provider = await self._resolve_provider(channel, provider_code)
        subject = render(template.subject, variables) if template.subject else None
        body = render(template.body, variables)
        message = NotificationMessage(
            template_key=template_key,
            channel=channel,
            provider_code=provider.code,
            to_address=to,
            subject=subject,
            body=body,
            status="pending",
            idempotency_key=idempotency_key,
        )
        self.repo.session.add(message)
        await self.repo.session.flush()
        return message

    async def _template(self, key: str, channel: str, locale: str) -> NotificationTemplate:
        row = await self.repo.get_template(key, channel, locale)
        if row is None:
            raise NotFound(f"Unknown template {key}")
        return row

    async def _resolve_provider(self, channel: str, code: str | None) -> NotificationProvider:
        if code:
            provider = await self.repo.get_provider(code)
            if provider is None or provider.channel != channel:
                raise NotFound(f"Unknown notification provider {code}")
            if not provider.enabled:
                raise RuleFailed(f"Provider {code} is disabled", code="PROVIDER_DISABLED")
            return provider
        enabled = await self.repo.enabled_providers(channel)
        if len(enabled) == 1:
            return enabled[0]
        if not enabled:
            raise RuleFailed(f"No enabled {channel} provider", code="PROVIDER_DISABLED")
        names = ", ".join(provider.code for provider in enabled)
        raise RuleFailed(f"Pass providerCode. Enabled providers: {names}", code="PROVIDER_REQUIRED")

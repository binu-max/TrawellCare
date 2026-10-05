import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notify.models import NotificationMessage, NotificationProvider, NotificationTemplate


class NotifyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_providers(self) -> list[NotificationProvider]:
        result = await self.session.scalars(select(NotificationProvider).order_by(NotificationProvider.code))
        return list(result)

    async def get_provider(self, code: str) -> NotificationProvider | None:
        return await self.session.scalar(select(NotificationProvider).where(NotificationProvider.code == code))

    async def enabled_providers(self, channel: str) -> list[NotificationProvider]:
        result = await self.session.scalars(
            select(NotificationProvider)
            .where(NotificationProvider.channel == channel, NotificationProvider.enabled.is_(True))
            .order_by(NotificationProvider.code)
        )
        return list(result)

    async def get_template(self, key: str, channel: str, locale: str) -> NotificationTemplate | None:
        return await self.session.scalar(
            select(NotificationTemplate).where(
                NotificationTemplate.key == key,
                NotificationTemplate.channel == channel,
                NotificationTemplate.locale == locale,
            )
        )

    async def get_message(self, message_id: uuid.UUID) -> NotificationMessage | None:
        return await self.session.get(NotificationMessage, message_id)

    async def due_messages(self) -> list[NotificationMessage]:
        moment = datetime.now(UTC)
        result = await self.session.scalars(
            select(NotificationMessage)
            .where(
                NotificationMessage.status.in_(("pending", "failed")),
                (NotificationMessage.next_attempt_at.is_(None)) | (NotificationMessage.next_attempt_at <= moment),
            )
            .order_by(NotificationMessage.created_at)
            .limit(20)
            .with_for_update(skip_locked=True)
        )
        return list(result)

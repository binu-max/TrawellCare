import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.travel.models import TravelOption, TravelRequest


class TravelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, request: TravelRequest) -> TravelRequest:
        self.session.add(request)
        await self.session.flush()
        return request

    async def get(self, request_id: uuid.UUID) -> TravelRequest | None:
        return await self.session.get(TravelRequest, request_id)

    async def options(self, request_id: uuid.UUID) -> list[TravelOption]:
        result = await self.session.scalars(
            select(TravelOption)
            .where(TravelOption.travel_request_id == request_id)
            .order_by(TravelOption.amount_minor, TravelOption.depart_at)
        )
        return list(result)

    async def option(self, request_id: uuid.UUID, option_id: uuid.UUID) -> TravelOption | None:
        row = await self.session.get(TravelOption, option_id)
        if row is None or row.travel_request_id != request_id:
            return None
        return row

    async def replace_options(self, request_id: uuid.UUID, options: list[TravelOption]) -> None:
        await self.session.execute(delete(TravelOption).where(TravelOption.travel_request_id == request_id))
        self.session.add_all(options)
        await self.session.flush()

    async def due_confirmations(self, now: datetime | None = None) -> list[TravelRequest]:
        moment = now or datetime.now(UTC)
        result = await self.session.scalars(
            select(TravelRequest)
            .where(
                TravelRequest.status == "confirming",
                (TravelRequest.next_attempt_at.is_(None)) | (TravelRequest.next_attempt_at <= moment),
            )
            .order_by(TravelRequest.created_at)
            .limit(20)
            .with_for_update(skip_locked=True)
        )
        return list(result)

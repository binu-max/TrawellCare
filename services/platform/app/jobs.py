import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.actor import clear_actor
from app.modules.cases.models import SlaTimer
from app.modules.control.models import Outbox

logger = logging.getLogger("trawellcare.platform.worker")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def fire_due_timers(session: AsyncSession) -> int:
    now = _now()
    rows = list(
        await session.scalars(
            select(SlaTimer)
            .where(SlaTimer.status == "armed", SlaTimer.due_at <= now)
            .limit(50)
            .with_for_update(skip_locked=True)
        )
    )
    for timer in rows:
        timer.status = "fired"
        timer.fired_at = now
        session.add(
            Outbox(
                type=timer.event_type,
                payload={"caseId": str(timer.case_id), "timerId": str(timer.id), "taskId": str(timer.task_id) if timer.task_id else None},
                status="pending",
            )
        )
    return len(rows)


async def publish_outbox(session: AsyncSession) -> int:
    now = _now()
    rows = list(
        await session.scalars(
            select(Outbox).where(Outbox.status == "pending").limit(50).with_for_update(skip_locked=True)
        )
    )
    for row in rows:
        row.status = "published"
        row.published_at = now
        logger.info("published %s %s", row.type, row.event_id)
    return len(rows)


async def process_once(factory: async_sessionmaker[AsyncSession]) -> None:
    clear_actor()
    async with factory() as session:
        try:
            await fire_due_timers(session)
            await publish_outbox(session)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("platform worker tick failed")

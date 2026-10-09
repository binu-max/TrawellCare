import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.control.models import AuditLog, Outbox


def audit(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    from_status: str | None = None,
    to_status: str | None = None,
    reason: str | None = None,
) -> None:
    session.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
        )
    )


def enqueue(session: AsyncSession, event_type: str, payload: dict) -> uuid.UUID:
    event_id = uuid.uuid4()
    session.add(Outbox(event_id=event_id, type=event_type, payload=payload, status="pending"))
    return event_id

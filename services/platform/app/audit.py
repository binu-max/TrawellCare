import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, event
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.actor import SYSTEM_USER_ID, current_actor


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform.users.id", use_alter=True),
        nullable=False,
    )
    modified_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform.users.id", use_alter=True),
        nullable=False,
    )


def install_audit_listener() -> None:
    @event.listens_for(Session, "before_flush")
    def stamp(session: Session, flush_context, instances) -> None:  # noqa: ARG001
        actor = current_actor()
        actor_id = actor.id if actor else SYSTEM_USER_ID
        now = _utcnow()
        for obj in session.new:
            if not isinstance(obj, AuditMixin):
                continue
            if obj.created_by is None:
                obj.created_by = actor_id
            if obj.modified_by is None:
                obj.modified_by = actor_id
            if obj.created_at is None:
                obj.created_at = now
            if obj.modified_at is None:
                obj.modified_at = now
        for obj in session.dirty:
            if isinstance(obj, AuditMixin):
                obj.modified_by = actor_id
                obj.modified_at = now

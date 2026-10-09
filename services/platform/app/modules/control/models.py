import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.audit import AuditMixin
from app.db import Base


class IdempotencyKey(AuditMixin, Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("actor_id", "key", name="uq_idempotency_actor_key"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[str] = mapped_column(Text)
    key: Mapped[str] = mapped_column(Text)
    request_hash: Mapped[str] = mapped_column(Text)
    response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, default=0)


class AuditLog(AuditMixin, Base):
    __tablename__ = "audit_log"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID]
    action: Mapped[str] = mapped_column(Text)
    from_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class Outbox(AuditMixin, Base):
    __tablename__ = "outbox"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4)
    type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(Text, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Inbox(AuditMixin, Base):
    __tablename__ = "inbox"
    __table_args__ = {"schema": "platform"}

    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(Text)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EventFailure(AuditMixin, Base):
    __tablename__ = "event_failures"
    __table_args__ = {"schema": "platform"}

    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefCounter(AuditMixin, Base):
    __tablename__ = "ref_counters"
    __table_args__ = {"schema": "platform"}

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, default=0)


class Disposition(AuditMixin, Base):
    __tablename__ = "dispositions"
    __table_args__ = {"schema": "platform"}

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    requires_reason: Mapped[bool] = mapped_column(default=False)
    active: Mapped[bool] = mapped_column(default=True)


class SlaPolicy(AuditMixin, Base):
    __tablename__ = "sla_policies"
    __table_args__ = {"schema": "platform"}

    policy_key: Mapped[str] = mapped_column(Text, primary_key=True)
    duration_seconds: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(Text)


class ConsentText(AuditMixin, Base):
    __tablename__ = "consent_texts"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    purpose: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True)

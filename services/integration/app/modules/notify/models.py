import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class NotificationProvider(Base):
    __tablename__ = "notification_providers"
    __table_args__ = {"schema": "integration"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(Text, unique=True)
    channel: Mapped[str] = mapped_column(Text)
    adapter_type: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"
    __table_args__ = (
        UniqueConstraint("key", "channel", "locale", name="uq_notification_template"),
        {"schema": "integration"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(Text, default="en")
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationMessage(Base):
    __tablename__ = "notification_messages"
    __table_args__ = {"schema": "integration"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    template_key: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text)
    provider_code: Mapped[str] = mapped_column(Text)
    to_address: Mapped[str] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

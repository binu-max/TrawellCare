import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = {"schema": "vault"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column()
    customer_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    case_party_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    classification: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    byte_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    object_key: Mapped[str] = mapped_column(Text)
    residency: Mapped[str] = mapped_column(Text, default="ae")
    scan_status: Mapped[str] = mapped_column(Text, default="pending")
    upload_status: Mapped[str] = mapped_column(Text, default="initiated")
    uploaded_by_kind: Mapped[str] = mapped_column(Text)
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column()
    visible_to_customer: Mapped[bool] = mapped_column(Boolean, default=True)
    retention_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DocumentAccessLog(Base):
    __tablename__ = "document_access_log"
    __table_args__ = {"schema": "vault"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column()
    actor_kind: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID] = mapped_column()
    action: Mapped[str] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

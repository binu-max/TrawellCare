import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.audit import AuditMixin
from app.db import Base


class Quote(AuditMixin, Base):
    __tablename__ = "quotes"
    __table_args__ = (
        Index("ix_quotes_case_status", "case_id", "status"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.cases.id"))
    care_plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.care_plans.id"), nullable=True)
    ref: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(Text, default="draft")
    current_version: Mapped[int] = mapped_column(Integer, default=1)


class QuoteVersion(AuditMixin, Base):
    __tablename__ = "quote_versions"
    __table_args__ = (
        UniqueConstraint("quote_id", "version", name="uq_quote_version"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    quote_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.quotes.id"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, default="draft")
    currency: Mapped[str] = mapped_column(Text)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=1)
    fx_base_currency: Mapped[str] = mapped_column(Text)
    fx_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QuoteAdjustment(AuditMixin, Base):
    __tablename__ = "quote_adjustments"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    quote_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.quote_versions.id"))
    kind: Mapped[str] = mapped_column(Text)
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)


class QuoteModule(AuditMixin, Base):
    __tablename__ = "quote_modules"
    __table_args__ = (
        Index("ix_quote_modules_decision", "quote_version_id", "patient_decision"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    quote_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.quote_versions.id"))
    module_type: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    supplier_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    currency: Mapped[str] = mapped_column(Text)
    amount_minor: Mapped[int] = mapped_column(Integer)
    price_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_decision: Mapped[str] = mapped_column(Text, default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    tariff_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("platform.tariff_versions.id"),
        nullable=True,
    )


class QuoteChangeRequest(AuditMixin, Base):
    __tablename__ = "quote_change_requests"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    quote_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.quotes.id"))
    from_version: Mapped[int] = mapped_column(Integer)
    to_version: Mapped[int] = mapped_column(Integer)
    module_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    reason: Mapped[str] = mapped_column(Text)


class Signoff(AuditMixin, Base):
    __tablename__ = "signoffs"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    quote_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.quote_versions.id"), unique=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.customers.id"))
    consent_text_version: Mapped[str] = mapped_column(Text)
    otp_challenge_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.otp_challenges.id"))
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Booking(AuditMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.cases.id"))
    quote_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.quotes.id"), unique=True)
    ref: Mapped[str] = mapped_column(Text, unique=True)
    currency: Mapped[str] = mapped_column(Text)
    amount_minor: Mapped[int] = mapped_column(Integer)
    payment_state: Mapped[str] = mapped_column(Text, default="unknown")


class ServiceLine(AuditMixin, Base):
    __tablename__ = "service_lines"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.bookings.id"))
    quote_module_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.quote_modules.id"), nullable=True)
    module_type: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="requested")
    currency: Mapped[str] = mapped_column(Text)
    amount_minor: Mapped[int] = mapped_column(Integer)


class ServiceLineEvent(AuditMixin, Base):
    __tablename__ = "service_line_events"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    service_line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.service_lines.id"))
    status: Mapped[str] = mapped_column(Text)
    supplier_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_confirmation: Mapped[bool] = mapped_column(default=False)


class ItineraryItem(AuditMixin, Base):
    __tablename__ = "itinerary_items"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.cases.id"))
    service_line_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.service_lines.id"), nullable=True)
    kind: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class DocumentRequirement(AuditMixin, Base):
    __tablename__ = "document_requirements"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.cases.id"))
    case_party_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.case_parties.id"), nullable=True)
    code: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="missing")
    vault_document_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class CancellationRequest(AuditMixin, Base):
    __tablename__ = "cancellation_requests"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.bookings.id"))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="requested")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.users.id"), nullable=True)

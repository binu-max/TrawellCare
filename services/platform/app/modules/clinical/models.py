import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.audit import AuditMixin
from app.db import Base


class ClinicalProfile(AuditMixin, Base):
    __tablename__ = "clinical_profiles"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.cases.id"), unique=True)
    allergies: Mapped[str | None] = mapped_column(Text, nullable=True)
    medications: Mapped[str | None] = mapped_column(Text, nullable=True)
    conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    prior_procedures: Mapped[str | None] = mapped_column(Text, nullable=True)


class TravelProfile(AuditMixin, Base):
    __tablename__ = "travel_profiles"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_party_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.case_parties.id"), unique=True)
    nationality: Mapped[str | None] = mapped_column(Text, nullable=True)
    passport_country: Mapped[str | None] = mapped_column(Text, nullable=True)
    passport_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)


class Consultation(AuditMixin, Base):
    __tablename__ = "consultations"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.cases.id"))
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.doctors.id"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    meeting_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="scheduled")
    rescheduled_from_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("platform.consultations.id"),
        nullable=True,
    )
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_identified: Mapped[str | None] = mapped_column(Text, nullable=True)
    clinical_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class CarePlan(AuditMixin, Base):
    __tablename__ = "care_plans"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.cases.id"))
    consultation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.consultations.id"), nullable=True)
    label: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="drafted")
    selection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class CarePlanModule(AuditMixin, Base):
    __tablename__ = "care_plan_modules"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    care_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.care_plans.id"))
    module_type: Mapped[str] = mapped_column(Text)
    tariff_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("platform.tariff_versions.id"),
        nullable=True,
    )
    currency: Mapped[str] = mapped_column(Text)
    amount_minor: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    price_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class MatchDecision(AuditMixin, Base):
    __tablename__ = "match_decisions"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.cases.id"))
    care_plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.care_plans.id"), nullable=True)
    tariff_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.tariff_versions.id"))
    score: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    rank: Mapped[int] = mapped_column(Integer)
    weights: Mapped[dict] = mapped_column(JSONB, default=dict)

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.audit import AuditMixin
from app.db import Base


class Enquiry(AuditMixin, Base):
    __tablename__ = "enquiries"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.customers.id"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("platform.cases.id", use_alter=True, name="fk_enquiry_case"),
        nullable=True,
    )
    extracted_slots: Mapped[dict] = mapped_column(JSONB, default=dict)
    campaign: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(Text, default="normal")
    status: Mapped[str] = mapped_column(Text, default="new")


class EnquiryTurn(AuditMixin, Base):
    __tablename__ = "enquiry_turns"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    enquiry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.enquiries.id"))
    ordinal: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)


class ContactAttempt(AuditMixin, Base):
    __tablename__ = "contact_attempts"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    enquiry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.enquiries.id"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.cases.id"), nullable=True)
    channel: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Qualification(AuditMixin, Base):
    __tablename__ = "qualifications"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    enquiry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.enquiries.id"))
    outcome: Mapped[str] = mapped_column(Text)
    disposition_code: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class Case(AuditMixin, Base):
    __tablename__ = "cases"
    __table_args__ = (
        Index("ix_cases_status_opened", "status", "opened_at"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ref: Mapped[str] = mapped_column(Text, unique=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.customers.id"))
    enquiry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("platform.enquiries.id", use_alter=True, name="fk_case_enquiry"),
        nullable=True,
    )
    stage: Mapped[str] = mapped_column(Text, default="preparation")
    status: Mapped[str] = mapped_column(Text, default="open")
    priority: Mapped[str] = mapped_column(Text, default="normal")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_disposition: Mapped[str | None] = mapped_column(Text, nullable=True)


class CaseParty(AuditMixin, Base):
    __tablename__ = "case_parties"
    __table_args__ = (
        Index(
            "uq_one_patient",
            "case_id",
            unique=True,
            postgresql_where=text("role = 'patient'"),
        ),
        Index(
            "uq_one_account_holder",
            "case_id",
            unique=True,
            postgresql_where=text("role = 'account_holder'"),
        ),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.cases.id"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.customers.id"), nullable=True)
    companion_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.companions.id"), nullable=True)
    role: Mapped[str] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(default=False)
    display_name: Mapped[str] = mapped_column(Text)
    phone_e164: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    sex: Mapped[str | None] = mapped_column(Text, nullable=True)


class CaseStageEvent(AuditMixin, Base):
    __tablename__ = "case_stage_events"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.cases.id"))
    from_stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_stage: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class CaseNote(AuditMixin, Base):
    __tablename__ = "case_notes"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.cases.id"))
    audience: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)


class CaseAssignment(AuditMixin, Base):
    __tablename__ = "case_assignments"
    __table_args__ = (
        Index(
            "uq_open_assignment_role",
            "case_id",
            "role",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.cases.id"))
    assignee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.users.id"))
    role: Mapped[str] = mapped_column(Text)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.users.id"), nullable=True)


class Task(AuditMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.cases.id"))
    type: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="open")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.users.id"), nullable=True)
    completed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.users.id"), nullable=True)


class SlaTimer(AuditMixin, Base):
    __tablename__ = "sla_timers"
    __table_args__ = (
        Index(
            "ix_sla_timers_armed",
            "due_at",
            postgresql_where=text("status = 'armed'"),
        ),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.cases.id"))
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.tasks.id"), nullable=True)
    policy_key: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, default="armed")
    fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_type: Mapped[str] = mapped_column(Text)

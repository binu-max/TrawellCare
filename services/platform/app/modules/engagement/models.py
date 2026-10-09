import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.audit import AuditMixin
from app.db import Base


class Review(AuditMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.cases.id"))
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.customers.id"))
    rating: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(Text, default="pending")


class Referral(AuditMixin, Base):
    __tablename__ = "referrals"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(Text, unique=True)
    referrer_customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.customers.id"))
    referred_customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("platform.customers.id"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, default="open")


class PointsEvent(AuditMixin, Base):
    __tablename__ = "points_events"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.customers.id"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.cases.id"), nullable=True)
    points: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FollowUp(AuditMixin, Base):
    __tablename__ = "follow_ups"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.cases.id"))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

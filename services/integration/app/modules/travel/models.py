import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TravelRequest(Base):
    __tablename__ = "travel_requests"
    __table_args__ = {"schema": "integration"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column()
    booking_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    vendor_code: Mapped[str] = mapped_column(Text)
    product: Mapped[str] = mapped_column(Text, default="flight")
    status: Mapped[str] = mapped_column(Text, default="draft")
    search_criteria: Mapped[dict] = mapped_column(JSONB, default=dict)
    supplier_session: Mapped[dict] = mapped_column(JSONB, default=dict)
    supplier_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmation_mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TravelOption(Base):
    __tablename__ = "travel_options"
    __table_args__ = {"schema": "integration"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    travel_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integration.travel_requests.id", ondelete="CASCADE")
    )
    supplier_offer_ref: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(Text)
    destination: Mapped[str] = mapped_column(Text)
    depart_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    arrive_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    airline_code: Mapped[str] = mapped_column(Text, default="")
    flight_number: Mapped[str] = mapped_column(Text, default="")
    stops: Mapped[int] = mapped_column(Integer, default=0)
    cabin: Mapped[str] = mapped_column(Text, default="")
    amount_minor: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(Text, default="")
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TravelCall(Base):
    __tablename__ = "travel_calls"
    __table_args__ = {"schema": "integration"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    travel_request_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    vendor_code: Mapped[str] = mapped_column(Text)
    operation: Mapped[str] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    request_body: Mapped[dict] = mapped_column(JSONB, default=dict)
    response_body: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

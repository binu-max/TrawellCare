import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.audit import AuditMixin
from app.db import Base


class User(AuditMixin, Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(CITEXT, unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="active")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StaffProfile(AuditMixin, Base):
    __tablename__ = "staff_profiles"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.users.id"), unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    phone_e164: Mapped[str | None] = mapped_column(Text, nullable=True)
    locale: Mapped[str] = mapped_column(Text, default="en")


class PhoneIdentity(AuditMixin, Base):
    __tablename__ = "phone_identities"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.users.id"))
    phone_e164: Mapped[str] = mapped_column(Text)
    phone_hash: Mapped[str] = mapped_column(Text, unique=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_primary: Mapped[bool] = mapped_column(default=True)
    channel: Mapped[str] = mapped_column(Text, default="sms")


class OtpChallenge(AuditMixin, Base):
    __tablename__ = "otp_challenges"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    phone_hash: Mapped[str] = mapped_column(Text)
    phone_e164: Mapped[str] = mapped_column(Text, default="")
    purpose: Mapped[str] = mapped_column(Text, default="login")
    code_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)


class EmailChallenge(AuditMixin, Base):
    __tablename__ = "email_challenges"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.users.id"))
    email: Mapped[str] = mapped_column(CITEXT)
    code_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefreshToken(AuditMixin, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.users.id"))
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    kind: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TotpSecret(AuditMixin, Base):
    __tablename__ = "totp_secrets"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.users.id"), unique=True)
    secret: Mapped[str] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Role(AuditMixin, Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, unique=True)


class UserRole(AuditMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.users.id"))
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.roles.id"))


class Customer(AuditMixin, Base):
    __tablename__ = "customers"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.users.id"), unique=True)
    display_name: Mapped[str] = mapped_column(Text, default="Traveller")
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    locale: Mapped[str] = mapped_column(Text, default="en")
    timezone: Mapped[str] = mapped_column(Text, default="Asia/Muscat")


class Companion(AuditMixin, Base):
    __tablename__ = "companions"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.customers.id"))
    display_name: Mapped[str] = mapped_column(Text)
    relationship: Mapped[str] = mapped_column(Text)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    nationality: Mapped[str | None] = mapped_column(Text, nullable=True)


class Consent(AuditMixin, Base):
    __tablename__ = "consents"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.customers.id"))
    purpose: Mapped[str] = mapped_column(Text)
    text_version: Mapped[str] = mapped_column(Text)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    channel: Mapped[str] = mapped_column(Text, default="web")
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)

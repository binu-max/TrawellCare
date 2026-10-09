import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.audit import AuditMixin
from app.db import Base


class Corridor(AuditMixin, Base):
    __tablename__ = "corridors"
    __table_args__ = (
        UniqueConstraint("origin_country", "destination_country", name="uq_corridor"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    origin_country: Mapped[str] = mapped_column(Text)
    destination_country: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True)


class Hospital(AuditMixin, Base):
    __tablename__ = "hospitals"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name_en: Mapped[str] = mapped_column(Text)
    name_ar: Mapped[str] = mapped_column(Text, default="")
    country: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text)
    accreditation: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=0)
    active: Mapped[bool] = mapped_column(default=True)


class Doctor(AuditMixin, Base):
    __tablename__ = "doctors"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.users.id"), nullable=True)
    name_en: Mapped[str] = mapped_column(Text)
    name_ar: Mapped[str] = mapped_column(Text, default="")
    specialty: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True)


class DoctorHospital(AuditMixin, Base):
    __tablename__ = "doctor_hospitals"
    __table_args__ = (
        UniqueConstraint("doctor_id", "hospital_id", name="uq_doctor_hospital"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.doctors.id"))
    hospital_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.hospitals.id"))


class Procedure(AuditMixin, Base):
    __tablename__ = "procedures"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    specialty: Mapped[str] = mapped_column(Text)
    name_en: Mapped[str] = mapped_column(Text)
    name_ar: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(default=True)


class HospitalProcedure(AuditMixin, Base):
    __tablename__ = "hospital_procedures"
    __table_args__ = (
        UniqueConstraint("hospital_id", "procedure_id", name="uq_hospital_procedure"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    hospital_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.hospitals.id"))
    procedure_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.procedures.id"))


class Package(AuditMixin, Base):
    __tablename__ = "packages"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    hospital_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.hospitals.id"), nullable=True)
    name_en: Mapped[str] = mapped_column(Text)
    name_ar: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(default=True)


class PackageComponent(AuditMixin, Base):
    __tablename__ = "package_components"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("platform.packages.id"))
    module_type: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class TariffVersion(AuditMixin, Base):
    __tablename__ = "tariff_versions"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    hospital_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.hospitals.id"), nullable=True)
    procedure_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.procedures.id"), nullable=True)
    package_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("platform.packages.id"), nullable=True)
    currency: Mapped[str] = mapped_column(Text)
    amount_minor: Mapped[int] = mapped_column(Integer)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaces_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

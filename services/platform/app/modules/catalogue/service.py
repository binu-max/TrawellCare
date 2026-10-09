from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tc_common import NotFound, RuleFailed

from app.access import assert_catalogue_write, assert_staff
from app.actor import Actor
from app.modules.catalogue.models import (
    Doctor,
    DoctorHospital,
    Hospital,
    HospitalProcedure,
    Package,
    PackageComponent,
    Procedure,
    TariffVersion,
)
from app.modules.catalogue.schemas import (
    DoctorBody,
    DoctorView,
    HospitalBody,
    HospitalView,
    PackageBody,
    PackageView,
    ProcedureBody,
    ProcedureView,
    TariffBody,
    TariffView,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hospital(row: Hospital) -> HospitalView:
    return HospitalView(
        id=row.id,
        name_en=row.name_en,
        name_ar=row.name_ar,
        country=row.country,
        city=row.city,
        accreditation=row.accreditation,
        rating=row.rating,
        active=row.active,
    )


async def list_hospitals(session: AsyncSession, actor: Actor) -> list[HospitalView]:
    assert_staff(actor)
    rows = await session.scalars(select(Hospital).order_by(Hospital.name_en))
    return [_hospital(row) for row in rows]


async def create_hospital(session: AsyncSession, actor: Actor, body: HospitalBody) -> HospitalView:
    assert_catalogue_write(actor)
    row = Hospital(
        name_en=body.name_en,
        name_ar=body.name_ar,
        country=body.country.upper(),
        city=body.city,
        accreditation=body.accreditation,
        rating=body.rating,
    )
    session.add(row)
    await session.flush()
    return _hospital(row)


async def patch_hospital_active(session: AsyncSession, actor: Actor, hospital_id, active: bool) -> HospitalView:
    assert_catalogue_write(actor)
    row = await session.get(Hospital, hospital_id)
    if row is None:
        raise NotFound("Hospital not found")
    row.active = active
    return _hospital(row)


async def list_doctors(session: AsyncSession, actor: Actor) -> list[DoctorView]:
    assert_staff(actor)
    rows = await session.scalars(select(Doctor).order_by(Doctor.name_en))
    return [
        DoctorView(
            id=row.id,
            name_en=row.name_en,
            name_ar=row.name_ar,
            specialty=row.specialty,
            user_id=row.user_id,
            active=row.active,
        )
        for row in rows
    ]


async def create_doctor(session: AsyncSession, actor: Actor, body: DoctorBody) -> DoctorView:
    assert_catalogue_write(actor)
    row = Doctor(name_en=body.name_en, name_ar=body.name_ar, specialty=body.specialty, user_id=body.user_id)
    session.add(row)
    await session.flush()
    if body.hospital_id:
        session.add(DoctorHospital(doctor_id=row.id, hospital_id=body.hospital_id))
    return DoctorView(
        id=row.id,
        name_en=row.name_en,
        name_ar=row.name_ar,
        specialty=row.specialty,
        user_id=row.user_id,
        active=row.active,
    )


async def list_procedures(session: AsyncSession, actor: Actor) -> list[ProcedureView]:
    assert_staff(actor)
    rows = await session.scalars(select(Procedure).order_by(Procedure.name_en))
    return [
        ProcedureView(id=row.id, slug=row.slug, specialty=row.specialty, name_en=row.name_en, name_ar=row.name_ar, active=row.active)
        for row in rows
    ]


async def create_procedure(session: AsyncSession, actor: Actor, body: ProcedureBody) -> ProcedureView:
    assert_catalogue_write(actor)
    row = Procedure(slug=body.slug, specialty=body.specialty, name_en=body.name_en, name_ar=body.name_ar)
    session.add(row)
    await session.flush()
    if body.hospital_id:
        session.add(HospitalProcedure(hospital_id=body.hospital_id, procedure_id=row.id))
    return ProcedureView(
        id=row.id,
        slug=row.slug,
        specialty=row.specialty,
        name_en=row.name_en,
        name_ar=row.name_ar,
        active=row.active,
    )


async def list_packages(session: AsyncSession, actor: Actor) -> list[PackageView]:
    assert_staff(actor)
    rows = await session.scalars(select(Package).order_by(Package.name_en))
    return [
        PackageView(id=row.id, name_en=row.name_en, name_ar=row.name_ar, hospital_id=row.hospital_id, active=row.active)
        for row in rows
    ]


async def create_package(session: AsyncSession, actor: Actor, body: PackageBody) -> PackageView:
    assert_catalogue_write(actor)
    row = Package(name_en=body.name_en, name_ar=body.name_ar, hospital_id=body.hospital_id)
    session.add(row)
    await session.flush()
    for index, component in enumerate(body.components):
        session.add(
            PackageComponent(
                package_id=row.id,
                module_type=component.module_type,
                description=component.description,
                sort_order=index,
            )
        )
    return PackageView(
        id=row.id,
        name_en=row.name_en,
        name_ar=row.name_ar,
        hospital_id=row.hospital_id,
        active=row.active,
    )


def _tariff(row: TariffVersion) -> TariffView:
    return TariffView(
        id=row.id,
        hospital_id=row.hospital_id,
        procedure_id=row.procedure_id,
        package_id=row.package_id,
        currency=row.currency,
        amount_minor=row.amount_minor,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
    )


async def list_tariffs(session: AsyncSession, actor: Actor) -> list[TariffView]:
    assert_staff(actor)
    now = _now()
    rows = await session.scalars(
        select(TariffVersion).where(TariffVersion.valid_to.is_(None) | (TariffVersion.valid_to > now))
    )
    return [_tariff(row) for row in rows]


async def create_tariff(session: AsyncSession, actor: Actor, body: TariffBody) -> TariffView:
    assert_catalogue_write(actor)
    if body.currency is None or len(body.currency) != 3:
        raise RuleFailed("currency must be a 3-letter code", code="VALIDATION_FAILED", status=400)
    row = TariffVersion(
        hospital_id=body.hospital_id,
        procedure_id=body.procedure_id,
        package_id=body.package_id,
        currency=body.currency.upper(),
        amount_minor=body.amount_minor,
        valid_from=body.valid_from or _now(),
    )
    session.add(row)
    await session.flush()
    return _tariff(row)


async def replace_tariff(session: AsyncSession, actor: Actor, tariff_id, body: TariffBody) -> TariffView:
    assert_catalogue_write(actor)
    current = await session.get(TariffVersion, tariff_id)
    if current is None:
        raise NotFound("Tariff not found")
    now = _now()
    if current.valid_to is None:
        current.valid_to = now
    row = TariffVersion(
        hospital_id=body.hospital_id or current.hospital_id,
        procedure_id=body.procedure_id or current.procedure_id,
        package_id=body.package_id or current.package_id,
        currency=(body.currency or current.currency).upper(),
        amount_minor=body.amount_minor,
        valid_from=body.valid_from or now,
        replaces_id=current.id,
    )
    session.add(row)
    await session.flush()
    return _tariff(row)

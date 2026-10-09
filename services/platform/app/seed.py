from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.actor import SYSTEM_USER_ID
from app.modules.catalogue.models import (
    Corridor,
    Doctor,
    DoctorHospital,
    Hospital,
    HospitalProcedure,
    Procedure,
    TariffVersion,
)
from app.modules.control.models import ConsentText, Disposition, SlaPolicy
from app.modules.identity.models import Role, StaffProfile, TotpSecret, User, UserRole
from app.security import hash_password
from app.settings import Settings

ROLE_NAMES = (
    "super_admin",
    "ops_admin",
    "case_manager",
    "wellness_curator",
    "doctor",
    "finance_maker",
    "finance_checker",
    "compliance_auditor",
    "content_editor",
)

STAFF = (
    ("ops@trawellcare.local", "Ops Admin", "ops_admin"),
    ("cm@trawellcare.local", "Case Manager", "case_manager"),
    ("curator@trawellcare.local", "Wellness Curator", "wellness_curator"),
    ("doctor@trawellcare.local", "Doctor", "doctor"),
    ("auditor@trawellcare.local", "Auditor", "compliance_auditor"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _staff(session: AsyncSession, settings: Settings, email: str, name: str, role_name: str) -> User:
    user = await session.scalar(select(User).where(User.email == email))
    if user:
        return user
    user = User(
        email=email,
        status="active",
        password_hash=hash_password(settings.staff_seed_password),
        email_verified_at=_now(),
    )
    session.add(user)
    await session.flush()
    session.add(StaffProfile(user_id=user.id, display_name=name))
    session.add(TotpSecret(user_id=user.id, secret=settings.staff_totp_secret, confirmed_at=_now()))
    role = await session.scalar(select(Role).where(Role.name == role_name))
    session.add(UserRole(user_id=user.id, role_id=role.id))
    return user


async def seed(session: AsyncSession, settings: Settings) -> None:
    if await session.get(User, SYSTEM_USER_ID) is None:
        session.add(User(id=SYSTEM_USER_ID, email="system@internal.trawellcare.local", status="active"))
        await session.flush()
    for name in ROLE_NAMES:
        if await session.scalar(select(Role).where(Role.name == name)) is None:
            session.add(Role(name=name))
    await session.flush()
    doctor_user = None
    for email, name, role_name in STAFF:
        user = await _staff(session, settings, email, name, role_name)
        if role_name == "doctor":
            doctor_user = user
    dispositions = (
        ("PROCEED_MEDICAL", "Proceed", False),
        ("NOT_FIT", "Not fit to travel", True),
        ("UNREACHABLE", "Unreachable", False),
    )
    for code, label, needs_reason in dispositions:
        if await session.get(Disposition, code) is None:
            session.add(Disposition(code=code, label=label, requires_reason=needs_reason, active=True))
    policies = (
        ("handoff", 4 * 60 * 60, "task.sla.breached.v1"),
        ("followup", 30 * 24 * 60 * 60, "followup.due.v1"),
    )
    for key, seconds, event_type in policies:
        if await session.get(SlaPolicy, key) is None:
            session.add(SlaPolicy(policy_key=key, duration_seconds=seconds, event_type=event_type))
    consent = await session.scalar(
        select(ConsentText).where(ConsentText.purpose == "quote_signoff", ConsentText.version == 1)
    )
    if consent is None:
        session.add(
            ConsentText(
                purpose="quote_signoff",
                version=1,
                body="I agree to the quoted care plan and the amount shown.",
                active=True,
            )
        )
    corridor = await session.scalar(
        select(Corridor).where(Corridor.origin_country == "OM", Corridor.destination_country == "IN")
    )
    if corridor is None:
        session.add(Corridor(origin_country="OM", destination_country="IN", active=True))
    hospital = await session.scalar(select(Hospital).where(Hospital.name_en == "Sample Hospital"))
    if hospital is None:
        hospital = Hospital(
            name_en="Sample Hospital",
            name_ar="مستشفى",
            country="IN",
            city="Chennai",
            accreditation="NABH",
            rating=Decimal("4.50"),
            active=True,
        )
        session.add(hospital)
        await session.flush()
        procedure = Procedure(slug="ivf", specialty="fertility", name_en="IVF", name_ar="أطفال الأنابيب", active=True)
        session.add(procedure)
        await session.flush()
        session.add(HospitalProcedure(hospital_id=hospital.id, procedure_id=procedure.id))
        doctor = Doctor(
            user_id=doctor_user.id if doctor_user else None,
            name_en="Dr Sample",
            name_ar="دكتور",
            specialty="fertility",
            active=True,
        )
        session.add(doctor)
        await session.flush()
        session.add(DoctorHospital(doctor_id=doctor.id, hospital_id=hospital.id))
        session.add(
            TariffVersion(
                hospital_id=hospital.id,
                procedure_id=procedure.id,
                currency="INR",
                amount_minor=1800000,
                valid_from=_now() - timedelta(days=1),
            )
        )
    await session.flush()

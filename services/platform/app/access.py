import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tc_common import Forbidden, NotFound

from app.actor import Actor

OPS = {"ops_admin", "super_admin"}
CASE_STAFF = {"case_manager", "wellness_curator"}
FINANCE = {"finance_maker", "finance_checker"}


def assert_staff(actor: Actor) -> None:
    if actor.kind != "staff":
        raise Forbidden("Staff token required")


def assert_catalogue_write(actor: Actor) -> None:
    assert_staff(actor)
    if actor.has_role("compliance_auditor") or actor.has_role(*FINANCE):
        raise Forbidden("This role cannot edit the catalogue")
    if not actor.has_role(*OPS, *CASE_STAFF):
        raise Forbidden("This role cannot edit the catalogue")


async def assert_case_access(session: AsyncSession, actor: Actor, case, *, write: bool) -> None:
    from app.modules.cases.models import CaseAssignment
    from app.modules.catalogue.models import Doctor
    from app.modules.clinical.models import Consultation

    if actor.kind == "service":
        return
    if actor.kind == "customer":
        if case.customer_id != actor.customer_id:
            raise NotFound("Case not found")
        return
    if actor.kind != "staff":
        raise NotFound("Case not found")
    if actor.has_role("compliance_auditor"):
        if write:
            raise Forbidden("Auditor cannot write")
        return
    if actor.has_role(*FINANCE) and not actor.has_role(*OPS):
        raise Forbidden("Finance has no platform case access")
    if actor.has_role(*OPS):
        return
    assigned = await session.scalar(
        select(CaseAssignment.id).where(
            CaseAssignment.case_id == case.id,
            CaseAssignment.assignee_id == actor.id,
            CaseAssignment.ended_at.is_(None),
        )
    )
    if assigned:
        return
    if actor.has_role("doctor"):
        doctor_ids = list(
            await session.scalars(select(Doctor.id).where(Doctor.user_id == actor.id))
        )
        if doctor_ids:
            hit = await session.scalar(
                select(Consultation.id).where(
                    Consultation.case_id == case.id,
                    Consultation.doctor_id.in_(doctor_ids),
                )
            )
            if hit:
                return
    raise NotFound("Case not found")


def customer_or_404(actor: Actor, customer_id: uuid.UUID) -> None:
    if actor.kind == "customer" and actor.customer_id != customer_id:
        raise NotFound("Case not found")

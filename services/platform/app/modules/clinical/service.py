from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tc_common import Forbidden, NotFound, RuleFailed

from app.access import OPS, assert_case_access, assert_staff
from app.actor import Actor
from app.events import audit, enqueue
from app.modules.cases.models import Case, CaseParty, Enquiry
from app.modules.catalogue.models import Doctor, Hospital, Procedure, TariffVersion
from app.modules.clinical.matching import WEIGHTS, TariffCandidate, rank_tariffs
from app.modules.clinical.models import (
    CarePlan,
    CarePlanModule,
    ClinicalProfile,
    Consultation,
    MatchDecision,
    TravelProfile,
)
from app.modules.clinical.schemas import (
    CarePlanModuleView,
    CarePlanView,
    ClinicalProfileBody,
    ClinicalProfileView,
    ConsultationBody,
    ConsultationView,
    MatchRow,
    ModulePatch,
    OutcomeBody,
    RescheduleBody,
    SelectPlan,
    TravelProfileBody,
    TravelProfileView,
)
from app.modules.quotes.service import materialize_quote

LABELS = ("A", "B", "C")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _case(session: AsyncSession, case_id) -> Case:
    row = await session.get(Case, case_id)
    if row is None:
        raise NotFound("Case not found")
    return row


def _consultation_view(row: Consultation, *, clinical: bool) -> ConsultationView:
    return ConsultationView(
        id=row.id,
        case_id=row.case_id,
        doctor_id=row.doctor_id,
        scheduled_at=row.scheduled_at,
        meeting_link=row.meeting_link,
        status=row.status,
        rescheduled_from_id=row.rescheduled_from_id,
        outcome=row.outcome if clinical else None,
        issue_identified=row.issue_identified if clinical else None,
        clinical_note=row.clinical_note if clinical else None,
    )


async def put_clinical_profile(session: AsyncSession, actor: Actor, case_id, body: ClinicalProfileBody) -> ClinicalProfileView:
    assert_staff(actor)
    case = await _case(session, case_id)
    await assert_case_access(session, actor, case, write=True)
    row = await session.scalar(select(ClinicalProfile).where(ClinicalProfile.case_id == case.id))
    if row is None:
        row = ClinicalProfile(case_id=case.id)
        session.add(row)
    row.allergies = body.allergies
    row.medications = body.medications
    row.conditions = body.conditions
    row.prior_procedures = body.prior_procedures
    await session.flush()
    return ClinicalProfileView(case_id=case.id, allergies=row.allergies, medications=row.medications, conditions=row.conditions, prior_procedures=row.prior_procedures)


async def get_clinical_profile(session: AsyncSession, actor: Actor, case_id) -> ClinicalProfileView:
    assert_staff(actor)
    case = await _case(session, case_id)
    await assert_case_access(session, actor, case, write=False)
    row = await session.scalar(select(ClinicalProfile).where(ClinicalProfile.case_id == case.id))
    if row is None:
        raise NotFound("Clinical profile not found")
    return ClinicalProfileView(
        case_id=case.id,
        allergies=row.allergies,
        medications=row.medications,
        conditions=row.conditions,
        prior_procedures=row.prior_procedures,
    )


async def put_travel_profile(session: AsyncSession, actor: Actor, case_id, party_id, body: TravelProfileBody) -> TravelProfileView:
    assert_staff(actor)
    case = await _case(session, case_id)
    await assert_case_access(session, actor, case, write=True)
    party = await session.get(CaseParty, party_id)
    if party is None or party.case_id != case.id:
        raise NotFound("Party not found")
    row = await session.scalar(select(TravelProfile).where(TravelProfile.case_party_id == party.id))
    if row is None:
        row = TravelProfile(case_party_id=party.id)
        session.add(row)
    row.nationality = body.nationality
    row.passport_country = body.passport_country
    row.passport_expiry = body.passport_expiry
    await session.flush()
    return TravelProfileView(
        case_party_id=party.id,
        nationality=row.nationality,
        passport_country=row.passport_country,
        passport_expiry=row.passport_expiry,
    )


async def book_consultation(session: AsyncSession, actor: Actor, case_id, body: ConsultationBody) -> ConsultationView:
    assert_staff(actor)
    case = await _case(session, case_id)
    await assert_case_access(session, actor, case, write=True)
    doctor = await session.get(Doctor, body.doctor_id)
    if doctor is None or not doctor.active:
        raise NotFound("Doctor not found")
    row = Consultation(
        case_id=case.id,
        doctor_id=doctor.id,
        scheduled_at=body.scheduled_at,
        meeting_link=body.meeting_link,
        status="scheduled",
    )
    session.add(row)
    await session.flush()
    enqueue(
        session,
        "consultation.booked.v1",
        {"caseId": str(case.id), "consultationId": str(row.id), "scheduledAt": body.scheduled_at.isoformat()},
    )
    audit(session, entity_type="consultation", entity_id=row.id, action="booked", to_status="scheduled")
    return _consultation_view(row, clinical=True)


async def list_consultations(session: AsyncSession, actor: Actor, case_id) -> list[ConsultationView]:
    case = await _case(session, case_id)
    await assert_case_access(session, actor, case, write=False)
    rows = await session.scalars(select(Consultation).where(Consultation.case_id == case.id).order_by(Consultation.scheduled_at))
    clinical = actor.kind == "staff"
    return [_consultation_view(row, clinical=clinical) for row in rows]


async def reschedule(session: AsyncSession, actor: Actor, consultation_id, body: RescheduleBody) -> ConsultationView:
    assert_staff(actor)
    current = await session.get(Consultation, consultation_id)
    if current is None:
        raise NotFound("Consultation not found")
    case = await _case(session, current.case_id)
    await assert_case_access(session, actor, case, write=True)
    current.status = "cancelled"
    current.cancel_reason = body.reason
    row = Consultation(
        case_id=current.case_id,
        doctor_id=current.doctor_id,
        scheduled_at=body.scheduled_at,
        meeting_link=body.meeting_link if body.meeting_link is not None else current.meeting_link,
        status="scheduled",
        rescheduled_from_id=current.id,
    )
    session.add(row)
    await session.flush()
    enqueue(
        session,
        "consultation.booked.v1",
        {"caseId": str(case.id), "consultationId": str(row.id), "scheduledAt": body.scheduled_at.isoformat()},
    )
    return _consultation_view(row, clinical=True)


async def record_outcome(session: AsyncSession, actor: Actor, consultation_id, body: OutcomeBody) -> ConsultationView:
    assert_staff(actor)
    row = await session.get(Consultation, consultation_id)
    if row is None:
        raise NotFound("Consultation not found")
    case = await _case(session, row.case_id)
    await assert_case_access(session, actor, case, write=True)
    doctor = await session.get(Doctor, row.doctor_id)
    if not actor.has_role(*OPS):
        if doctor is None or doctor.user_id != actor.id:
            raise Forbidden("Only the assigned doctor can record the outcome")
    row.status = "completed"
    row.outcome = body.outcome
    row.issue_identified = body.issue_identified
    row.clinical_note = body.clinical_note
    audit(session, entity_type="consultation", entity_id=row.id, action="outcome", to_status="completed")
    return _consultation_view(row, clinical=True)


async def _candidates(session: AsyncSession) -> list[TariffCandidate]:
    now = _now()
    rows = await session.execute(
        select(TariffVersion, Procedure, Hospital)
        .join(Procedure, Procedure.id == TariffVersion.procedure_id)
        .join(Hospital, Hospital.id == TariffVersion.hospital_id)
        .where(TariffVersion.valid_from <= now)
        .where(TariffVersion.valid_to.is_(None) | (TariffVersion.valid_to > now))
        .where(Hospital.active.is_(True))
        .where(Procedure.active.is_(True))
    )
    found = []
    for tariff, procedure, hospital in rows:
        found.append(
            TariffCandidate(
                id=tariff.id,
                procedure_slug=procedure.slug,
                procedure_name=procedure.name_en,
                specialty=procedure.specialty,
                amount_minor=tariff.amount_minor,
                currency=tariff.currency,
                rating=float(hospital.rating or 0),
                hospital_name=hospital.name_en,
                title=f"{procedure.name_en} at {hospital.name_en}",
            )
        )
    return found


def _module_view(row: CarePlanModule) -> CarePlanModuleView:
    return CarePlanModuleView(
        id=row.id,
        module_type=row.module_type,
        title=row.title,
        currency=row.currency,
        amount_minor=row.amount_minor,
        tariff_version_id=row.tariff_version_id,
    )


async def _plan_view(session: AsyncSession, plan: CarePlan) -> CarePlanView:
    modules = await session.scalars(select(CarePlanModule).where(CarePlanModule.care_plan_id == plan.id))
    return CarePlanView(
        id=plan.id,
        label=plan.label,
        status=plan.status,
        selection_reason=plan.selection_reason,
        modules=[_module_view(row) for row in modules],
    )


async def list_care_plans(session: AsyncSession, actor: Actor, case_id) -> list[CarePlanView]:
    assert_staff(actor)
    case = await _case(session, case_id)
    await assert_case_access(session, actor, case, write=False)
    plans = await session.scalars(select(CarePlan).where(CarePlan.case_id == case.id).order_by(CarePlan.label))
    return [await _plan_view(session, plan) for plan in plans]


async def draft_care_plans(session: AsyncSession, actor: Actor, case_id) -> list[CarePlanView]:
    assert_staff(actor)
    case = await _case(session, case_id)
    await assert_case_access(session, actor, case, write=True)
    existing = list(await session.scalars(select(CarePlan).where(CarePlan.case_id == case.id)))
    if existing:
        raise RuleFailed("Care plans already exist for this case", code="CONFLICT", status=409)
    enquiry = await session.get(Enquiry, case.enquiry_id) if case.enquiry_id else None
    interest = ""
    if enquiry:
        interest = str((enquiry.extracted_slots or {}).get("procedure_interest") or "")
    ranked = rank_tariffs(await _candidates(session), interest)
    consultation = await session.scalar(
        select(Consultation)
        .where(Consultation.case_id == case.id, Consultation.status != "cancelled")
        .order_by(Consultation.scheduled_at.desc())
    )
    plans: list[CarePlan] = []
    for index, label in enumerate(LABELS):
        plan = CarePlan(
            case_id=case.id,
            consultation_id=consultation.id if consultation else None,
            label=label,
            status="drafted",
        )
        session.add(plan)
        await session.flush()
        if index < len(ranked):
            candidate, score = ranked[index]
            session.add(
                CarePlanModule(
                    care_plan_id=plan.id,
                    module_type="hospital",
                    tariff_version_id=candidate.id,
                    currency=candidate.currency,
                    amount_minor=candidate.amount_minor,
                    title=candidate.title,
                )
            )
            session.add(
                MatchDecision(
                    case_id=case.id,
                    care_plan_id=plan.id,
                    tariff_version_id=candidate.id,
                    score=score,
                    rank=index + 1,
                    weights=WEIGHTS,
                )
            )
        else:
            session.add(
                CarePlanModule(
                    care_plan_id=plan.id,
                    module_type="hospital",
                    currency="OMR",
                    amount_minor=0,
                    title=f"Manual option {label}",
                )
            )
        plans.append(plan)
    enqueue(session, "care_plans.drafted.v1", {"caseId": str(case.id)})
    audit(session, entity_type="case", entity_id=case.id, action="care_plans_drafted", to_status="drafted")
    return [await _plan_view(session, plan) for plan in plans]


async def patch_plan_module(session: AsyncSession, actor: Actor, plan_id, module_id, body: ModulePatch) -> CarePlanModuleView:
    assert_staff(actor)
    plan = await session.get(CarePlan, plan_id)
    if plan is None or plan.status != "drafted":
        raise RuleFailed("Only a drafted plan can be edited", code="CONFLICT", status=409)
    case = await _case(session, plan.case_id)
    await assert_case_access(session, actor, case, write=True)
    module = await session.get(CarePlanModule, module_id)
    if module is None or module.care_plan_id != plan.id:
        raise NotFound("Module not found")
    if body.amount_minor is not None and body.amount_minor != module.amount_minor and not body.price_override_reason:
        raise RuleFailed("A price change requires a reason", code="VALIDATION_FAILED", status=400)
    if body.title is not None:
        module.title = body.title
    if body.amount_minor is not None:
        module.amount_minor = body.amount_minor
        module.price_override_reason = body.price_override_reason
    if body.currency is not None:
        module.currency = body.currency.upper()
    return _module_view(module)


async def select_plan(session: AsyncSession, actor: Actor, plan_id, body: SelectPlan) -> dict:
    assert_staff(actor)
    if not body.selection_reason.strip():
        raise RuleFailed("selectionReason is required", code="VALIDATION_FAILED", status=400)
    plan = await session.get(CarePlan, plan_id)
    if plan is None:
        raise NotFound("Care plan not found")
    case = await _case(session, plan.case_id)
    await assert_case_access(session, actor, case, write=True)
    siblings = await session.scalars(select(CarePlan).where(CarePlan.case_id == case.id))
    for sibling in siblings:
        if sibling.id == plan.id:
            sibling.status = "selected"
            sibling.selection_reason = body.selection_reason
        elif sibling.status != "discarded":
            sibling.status = "discarded"
    quote = await materialize_quote(session, case, plan)
    audit(session, entity_type="care_plan", entity_id=plan.id, action="selected", to_status="selected", reason=body.selection_reason)
    return quote


async def match_preview(session: AsyncSession, actor: Actor, case_id) -> list[MatchRow]:
    assert_staff(actor)
    case = await _case(session, case_id)
    await assert_case_access(session, actor, case, write=False)
    enquiry = await session.get(Enquiry, case.enquiry_id) if case.enquiry_id else None
    interest = str((enquiry.extracted_slots or {}).get("procedure_interest") or "") if enquiry else ""
    ranked = rank_tariffs(await _candidates(session), interest)
    return [
        MatchRow(
            tariff_version_id=candidate.id,
            score=score,
            rank=index + 1,
            title=candidate.title,
            amount_minor=candidate.amount_minor,
            currency=candidate.currency,
        )
        for index, (candidate, score) in enumerate(ranked)
    ]

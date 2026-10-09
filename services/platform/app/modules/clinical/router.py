from uuid import UUID

from fastapi import APIRouter

from app.deps import SessionDep, StaffDep, UserDep
from app.http import dump
from app.modules.clinical import service
from app.modules.clinical.schemas import (
    ClinicalProfileBody,
    ConsultationBody,
    ModulePatch,
    OutcomeBody,
    RescheduleBody,
    SelectPlan,
    TravelProfileBody,
)

router = APIRouter(tags=["clinical"])


@router.put("/v1/cases/{case_id}/clinical-profile")
async def put_profile(case_id: UUID, body: ClinicalProfileBody, actor: StaffDep, session: SessionDep):
    return dump(await service.put_clinical_profile(session, actor, case_id, body))


@router.get("/v1/cases/{case_id}/clinical-profile")
async def get_profile(case_id: UUID, actor: StaffDep, session: SessionDep):
    return dump(await service.get_clinical_profile(session, actor, case_id))


@router.put("/v1/cases/{case_id}/parties/{party_id}/travel-profile")
async def travel_profile(
    case_id: UUID,
    party_id: UUID,
    body: TravelProfileBody,
    actor: StaffDep,
    session: SessionDep,
):
    return dump(await service.put_travel_profile(session, actor, case_id, party_id, body))


@router.post("/v1/cases/{case_id}/consultations", status_code=201)
async def book(case_id: UUID, body: ConsultationBody, actor: StaffDep, session: SessionDep):
    return dump(await service.book_consultation(session, actor, case_id, body))


@router.get("/v1/cases/{case_id}/consultations")
async def consultations(case_id: UUID, actor: UserDep, session: SessionDep):
    return dump(await service.list_consultations(session, actor, case_id))


@router.post("/v1/consultations/{consultation_id}/reschedule", status_code=201)
async def reschedule(consultation_id: UUID, body: RescheduleBody, actor: StaffDep, session: SessionDep):
    return dump(await service.reschedule(session, actor, consultation_id, body))


@router.post("/v1/consultations/{consultation_id}/outcome")
async def outcome(consultation_id: UUID, body: OutcomeBody, actor: StaffDep, session: SessionDep):
    return dump(await service.record_outcome(session, actor, consultation_id, body))


@router.get("/v1/cases/{case_id}/care-plans")
async def care_plans(case_id: UUID, actor: StaffDep, session: SessionDep):
    return dump(await service.list_care_plans(session, actor, case_id))


@router.post("/v1/cases/{case_id}/care-plans", status_code=201)
async def draft_plans(case_id: UUID, actor: StaffDep, session: SessionDep):
    return dump(await service.draft_care_plans(session, actor, case_id))


@router.patch("/v1/care-plans/{plan_id}/modules/{module_id}")
async def patch_module(plan_id: UUID, module_id: UUID, body: ModulePatch, actor: StaffDep, session: SessionDep):
    return dump(await service.patch_plan_module(session, actor, plan_id, module_id, body))


@router.post("/v1/care-plans/{plan_id}/select")
async def select_plan(plan_id: UUID, body: SelectPlan, actor: StaffDep, session: SessionDep):
    return await service.select_plan(session, actor, plan_id, body)


@router.get("/v1/staff/cases/{case_id}/match-preview")
async def preview(case_id: UUID, actor: StaffDep, session: SessionDep):
    return dump(await service.match_preview(session, actor, case_id))

from uuid import UUID

from fastapi import APIRouter

from app.deps import CustomerDep, KeyDep, ServiceDep, SessionDep, StaffDep, UserDep
from app.http import command, dump
from app.modules.cases import service
from app.modules.cases.schemas import (
    AssignmentBody,
    CloseBody,
    ContactAttemptBody,
    CreateEnquiry,
    NoteBody,
    PartyBody,
    PriorityPatch,
    QualificationBody,
    StageBody,
)

router = APIRouter(tags=["cases"])


@router.post("/v1/enquiries", status_code=201)
async def create_enquiry(body: CreateEnquiry, actor: ServiceDep, session: SessionDep, key: KeyDep):
    return await command(session, actor, key, body.model_dump(mode="json"), 201, lambda: service.create_enquiry(session, body))


@router.get("/v1/enquiries/{enquiry_id}")
async def get_enquiry(enquiry_id: UUID, actor: StaffDep, session: SessionDep):
    return dump(await service.get_enquiry(session, actor, enquiry_id))


@router.get("/v1/enquiries/{enquiry_id}/turns")
async def turns(enquiry_id: UUID, actor: StaffDep, session: SessionDep):
    return dump(await service.list_turns(session, actor, enquiry_id))


@router.post("/v1/enquiries/{enquiry_id}/contact-attempts", status_code=201)
async def contact(enquiry_id: UUID, body: ContactAttemptBody, actor: StaffDep, session: SessionDep):
    return await service.add_contact_attempt(session, actor, enquiry_id, body)


@router.post("/v1/enquiries/{enquiry_id}/qualification")
async def qualify(enquiry_id: UUID, body: QualificationBody, actor: StaffDep, session: SessionDep, key: KeyDep):
    return await command(
        session,
        actor,
        key,
        body.model_dump(mode="json"),
        200,
        lambda: service.qualify(session, actor, enquiry_id, body),
    )


@router.post("/v1/tasks/{task_id}/complete")
async def complete_task(task_id: UUID, actor: StaffDep, session: SessionDep):
    return dump(await service.complete_task(session, actor, task_id))


@router.patch("/v1/cases/{case_id}")
async def priority(case_id: UUID, body: PriorityPatch, actor: StaffDep, session: SessionDep):
    return dump(await service.patch_priority(session, actor, case_id, body))


@router.post("/v1/cases/{case_id}/parties", status_code=201)
async def parties(case_id: UUID, body: PartyBody, actor: StaffDep, session: SessionDep):
    return dump(await service.upsert_party(session, actor, case_id, body))


@router.post("/v1/cases/{case_id}/stage")
async def stage(case_id: UUID, body: StageBody, actor: StaffDep, session: SessionDep):
    return dump(await service.change_stage(session, actor, case_id, body))


@router.post("/v1/cases/{case_id}/notes", status_code=201)
async def notes(case_id: UUID, body: NoteBody, actor: UserDep, session: SessionDep):
    return dump(await service.add_note(session, actor, case_id, body))


@router.post("/v1/cases/{case_id}/close")
async def close_case(case_id: UUID, body: CloseBody, actor: StaffDep, session: SessionDep, key: KeyDep):
    return await command(
        session,
        actor,
        key,
        {"caseId": str(case_id), **body.model_dump(mode="json")},
        200,
        lambda: service.close_case(session, actor, case_id, body),
    )


@router.post("/v1/cases/{case_id}/assignments", status_code=201)
async def assign(case_id: UUID, body: AssignmentBody, actor: StaffDep, session: SessionDep):
    return dump(await service.assign(session, actor, case_id, body))


@router.post("/v1/cases/{case_id}/assignments/{assignment_id}/end")
async def end_assignment(case_id: UUID, assignment_id: UUID, actor: StaffDep, session: SessionDep):
    return dump(await service.end_assignment(session, actor, case_id, assignment_id))


@router.get("/v1/customers/me/cases")
async def my_cases(
    actor: CustomerDep,
    session: SessionDep,
    cursor: str | None = None,
    limit: int | None = None,
):
    return await service.my_cases(session, actor, cursor, limit)


@router.get("/v1/cases/{case_id}")
async def get_case(case_id: UUID, actor: UserDep, session: SessionDep):
    return dump(await service.get_case(session, actor, case_id))


@router.get("/v1/cases/{case_id}/journey")
async def journey(case_id: UUID, actor: UserDep, session: SessionDep):
    return dump(await service.journey(session, actor, case_id))


@router.get("/v1/cases/{case_id}/tasks")
async def tasks(case_id: UUID, actor: UserDep, session: SessionDep, audience: str | None = None):
    return dump(await service.list_tasks(session, actor, case_id, audience))


@router.get("/v1/staff/queue")
async def queue(
    actor: StaffDep,
    session: SessionDep,
    assignee: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
):
    return await service.staff_queue(
        session,
        actor,
        assignee=assignee,
        status=status,
        priority=priority,
        cursor=cursor,
        limit=limit,
    )


@router.get("/v1/staff/sla-breaches")
async def breaches(actor: StaffDep, session: SessionDep):
    return await service.sla_breaches(session, actor)


@router.get("/v1/staff/dispositions")
async def dispositions(actor: StaffDep, session: SessionDep):
    return await service.list_dispositions(session, actor)

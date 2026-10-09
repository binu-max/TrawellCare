from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tc_common import NotFound, RuleFailed

from app.access import assert_case_access, assert_staff
from app.actor import Actor
from app.events import audit, enqueue
from app.modules.cases.models import (
    Case,
    CaseAssignment,
    CaseNote,
    CaseParty,
    CaseStageEvent,
    ContactAttempt,
    Enquiry,
    EnquiryTurn,
    Qualification,
    SlaTimer,
    Task,
)
from app.modules.cases.schemas import (
    AssignmentBody,
    AssignmentView,
    CaseSummary,
    CaseView,
    CloseBody,
    ContactAttemptBody,
    CreateEnquiry,
    EnquiryCreated,
    EnquiryView,
    JourneyEvent,
    JourneyView,
    NoteBody,
    NoteView,
    PartyBody,
    PartyView,
    PriorityPatch,
    QualificationBody,
    StageBody,
    TaskView,
    TurnView,
)
from app.modules.control.models import Disposition, SlaPolicy
from app.modules.identity.models import Companion, Customer, StaffProfile
from app.paging import decode_offset, encode_offset, page
from app.refs import next_ref

REQUIRED_SLOTS = (
    "patient_name",
    "home_country",
    "home_city",
    "procedure_interest",
    "destination_interest",
    "travel_window",
    "budget_band",
    "companion_count",
    "language",
)
STAGES = ["preparation", "planning", "treatment", "recovery", "ongoing_support"]
BUDGETS = {"low", "medium", "high"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_slots(slots: dict) -> dict:
    missing = []
    for key in REQUIRED_SLOTS:
        value = slots.get(key)
        if key == "companion_count":
            if value is None or value == "":
                missing.append(key)
            continue
        if value is None or str(value).strip() == "":
            missing.append(key)
    if missing:
        raise RuleFailed("Missing slots: " + ", ".join(missing), code="SLOTS_INCOMPLETE")
    country = str(slots["home_country"]).strip().upper()
    if len(country) != 2:
        raise RuleFailed("home_country must be an ISO country code", code="SLOTS_INCOMPLETE")
    if str(slots["budget_band"]) not in BUDGETS:
        raise RuleFailed("budget_band must be low, medium, or high", code="SLOTS_INCOMPLETE")
    try:
        count = int(slots["companion_count"])
    except (TypeError, ValueError) as exc:
        raise RuleFailed("companion_count must be a number", code="SLOTS_INCOMPLETE") from exc
    if count < 0 or count > 9:
        raise RuleFailed("companion_count must be from 0 to 9", code="SLOTS_INCOMPLETE")
    cleaned = dict(slots)
    cleaned["home_country"] = country
    cleaned["companion_count"] = count
    return cleaned


async def _policy(session: AsyncSession, key: str) -> SlaPolicy:
    row = await session.get(SlaPolicy, key)
    if row is None:
        raise RuleFailed(f"SLA policy {key} is not configured", code="RULE_FAILED")
    return row


async def _load_case(session: AsyncSession, case_id) -> Case:
    row = await session.get(Case, case_id)
    if row is None:
        raise NotFound("Case not found")
    return row


def _party_view(row: CaseParty) -> PartyView:
    return PartyView(
        id=row.id,
        role=row.role,
        display_name=row.display_name,
        phone_e164=row.phone_e164,
        date_of_birth=row.date_of_birth,
        sex=row.sex,
        companion_id=row.companion_id,
        is_primary=row.is_primary,
    )


async def _case_view(session: AsyncSession, case: Case) -> CaseView:
    parties = await session.scalars(select(CaseParty).where(CaseParty.case_id == case.id))
    return CaseView(
        id=case.id,
        ref=case.ref,
        customer_id=case.customer_id,
        stage=case.stage,
        status=case.status,
        priority=case.priority,
        opened_at=case.opened_at,
        closed_at=case.closed_at,
        parties=[_party_view(row) for row in parties],
    )


async def create_enquiry(session: AsyncSession, body: CreateEnquiry) -> EnquiryCreated:
    existing = await session.scalar(select(Enquiry).where(Enquiry.conversation_id == body.conversation_id))
    if existing and existing.case_id:
        case = await session.get(Case, existing.case_id)
        return EnquiryCreated(enquiry_id=existing.id, case_id=existing.case_id, case_ref=case.ref if case else "")
    slots = _validate_slots(body.extracted_slots)
    customer = await session.get(Customer, body.customer_id)
    if customer is None:
        raise NotFound("Customer not found")
    if customer.display_name == "Traveller" and slots.get("patient_name"):
        customer.display_name = str(slots["patient_name"])
        customer.country = slots["home_country"]
    enquiry = existing or Enquiry(
        conversation_id=body.conversation_id,
        customer_id=customer.id,
        extracted_slots=slots,
        campaign=body.campaign,
        status="new",
    )
    if existing is None:
        session.add(enquiry)
        await session.flush()
    else:
        enquiry.extracted_slots = slots
    for turn in body.turns:
        session.add(
            EnquiryTurn(
                enquiry_id=enquiry.id,
                ordinal=turn.ordinal,
                role=turn.role,
                content=turn.content,
            )
        )
    ref = await next_ref(session, "case")
    now = _now()
    case = Case(
        ref=ref,
        customer_id=customer.id,
        enquiry_id=enquiry.id,
        stage="preparation",
        status="open",
        opened_at=now,
    )
    session.add(case)
    await session.flush()
    enquiry.case_id = case.id
    name = str(slots.get("patient_name") or customer.display_name)
    session.add(
        CaseParty(
            case_id=case.id,
            customer_id=customer.id,
            role="account_holder",
            is_primary=True,
            display_name=name,
        )
    )
    session.add(
        CaseParty(
            case_id=case.id,
            customer_id=customer.id,
            role="patient",
            is_primary=True,
            display_name=name,
        )
    )
    session.add(CaseStageEvent(case_id=case.id, from_stage=None, to_stage="preparation", reason="handoff"))
    policy = await _policy(session, "handoff")
    manager = await _first_user_with_role(session, "case_manager")
    task = Task(
        case_id=case.id,
        type="handoff_call",
        title="Call the patient",
        status="open",
        due_at=now + timedelta(seconds=policy.duration_seconds),
        assignee_id=manager,
    )
    session.add(task)
    await session.flush()
    if manager:
        session.add(
            CaseAssignment(
                case_id=case.id,
                assignee_id=manager,
                role="case_manager",
                assigned_at=now,
            )
        )
    session.add(
        SlaTimer(
            case_id=case.id,
            task_id=task.id,
            policy_key="handoff",
            due_at=task.due_at,
            status="armed",
            event_type=policy.event_type,
        )
    )
    audit(session, entity_type="enquiry", entity_id=enquiry.id, action="created", to_status="new")
    audit(session, entity_type="case", entity_id=case.id, action="opened", to_status="preparation")
    enqueue(session, "enquiry.created.v1", {"enquiryId": str(enquiry.id), "caseId": str(case.id), "customerId": str(customer.id)})
    enqueue(session, "case.opened.v1", {"caseId": str(case.id), "customerId": str(customer.id), "caseRef": case.ref})
    return EnquiryCreated(enquiry_id=enquiry.id, case_id=case.id, case_ref=case.ref)


async def _first_user_with_role(session: AsyncSession, role_name: str):
    from app.modules.identity.models import Role, UserRole

    return await session.scalar(
        select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.name == role_name).limit(1)
    )


async def get_enquiry(session: AsyncSession, actor: Actor, enquiry_id) -> EnquiryView:
    assert_staff(actor)
    row = await session.get(Enquiry, enquiry_id)
    if row is None:
        raise NotFound("Enquiry not found")
    if row.case_id:
        case = await _load_case(session, row.case_id)
        await assert_case_access(session, actor, case, write=False)
    return EnquiryView(
        id=row.id,
        conversation_id=row.conversation_id,
        customer_id=row.customer_id,
        case_id=row.case_id,
        extracted_slots=row.extracted_slots,
        campaign=row.campaign,
        priority=row.priority,
        status=row.status,
    )


async def list_turns(session: AsyncSession, actor: Actor, enquiry_id) -> list[TurnView]:
    await get_enquiry(session, actor, enquiry_id)
    rows = await session.scalars(
        select(EnquiryTurn).where(EnquiryTurn.enquiry_id == enquiry_id).order_by(EnquiryTurn.ordinal)
    )
    return [TurnView(ordinal=row.ordinal, role=row.role, content=row.content) for row in rows]


async def add_contact_attempt(session: AsyncSession, actor: Actor, enquiry_id, body: ContactAttemptBody) -> dict:
    assert_staff(actor)
    enquiry = await session.get(Enquiry, enquiry_id)
    if enquiry is None:
        raise NotFound("Enquiry not found")
    if body.channel not in ("call", "sms", "whatsapp", "email"):
        raise RuleFailed("Unknown channel", code="VALIDATION_FAILED", status=400)
    if body.outcome not in ("reached", "no_answer", "voicemail", "wrong_number"):
        raise RuleFailed("Unknown outcome", code="VALIDATION_FAILED", status=400)
    if enquiry.case_id:
        case = await _load_case(session, enquiry.case_id)
        await assert_case_access(session, actor, case, write=True)
    session.add(
        ContactAttempt(
            enquiry_id=enquiry.id,
            case_id=enquiry.case_id,
            channel=body.channel,
            outcome=body.outcome,
            notes=body.notes,
            attempted_at=_now(),
        )
    )
    if enquiry.status == "new":
        if body.outcome == "reached":
            enquiry.status = "contacted"
        else:
            misses = await session.scalar(
                select(func.count())
                .select_from(ContactAttempt)
                .where(
                    ContactAttempt.enquiry_id == enquiry.id,
                    ContactAttempt.outcome.in_(("no_answer", "wrong_number", "voicemail")),
                )
            )
            if misses is not None and misses + 1 >= 3:
                enquiry.status = "unreachable"
    return {"status": enquiry.status}


async def qualify(session: AsyncSession, actor: Actor, enquiry_id, body: QualificationBody) -> dict:
    assert_staff(actor)
    enquiry = await session.get(Enquiry, enquiry_id)
    if enquiry is None or enquiry.case_id is None:
        raise NotFound("Enquiry not found")
    case = await _load_case(session, enquiry.case_id)
    await assert_case_access(session, actor, case, write=True)
    if body.outcome not in ("qualified", "not_qualified"):
        raise RuleFailed("Outcome must be qualified or not_qualified", code="VALIDATION_FAILED", status=400)
    disposition = await session.get(Disposition, body.disposition_code)
    if disposition is None or not disposition.active:
        raise RuleFailed("Unknown disposition", code="VALIDATION_FAILED", status=400)
    if disposition.requires_reason and not (body.reason and body.reason.strip()):
        raise RuleFailed("This disposition requires a reason", code="VALIDATION_FAILED", status=400)
    previous = enquiry.status
    enquiry.status = "qualified" if body.outcome == "qualified" else "not_qualified"
    session.add(
        Qualification(
            enquiry_id=enquiry.id,
            outcome=body.outcome,
            disposition_code=body.disposition_code,
            reason=body.reason,
        )
    )
    await _cancel_handoff(session, case.id, met=True)
    audit(
        session,
        entity_type="enquiry",
        entity_id=enquiry.id,
        action="qualified",
        from_status=previous,
        to_status=enquiry.status,
        reason=body.reason,
    )
    return {"status": enquiry.status}


async def _cancel_handoff(session: AsyncSession, case_id, *, met: bool) -> None:
    now = _now()
    timers = await session.scalars(
        select(SlaTimer).where(SlaTimer.case_id == case_id, SlaTimer.policy_key == "handoff", SlaTimer.status == "armed")
    )
    for timer in timers:
        timer.status = "met" if met else "cancelled"
        timer.fired_at = now
    tasks = await session.scalars(
        select(Task).where(Task.case_id == case_id, Task.type == "handoff_call", Task.status == "open")
    )
    for task in tasks:
        task.status = "completed" if met else "cancelled"
        task.completed_at = now


async def complete_task(session: AsyncSession, actor: Actor, task_id) -> TaskView:
    assert_staff(actor)
    task = await session.get(Task, task_id)
    if task is None:
        raise NotFound("Task not found")
    case = await _load_case(session, task.case_id)
    await assert_case_access(session, actor, case, write=True)
    now = _now()
    task.status = "completed"
    task.completed_at = now
    task.completed_by = actor.id
    timers = await session.scalars(
        select(SlaTimer).where(SlaTimer.task_id == task.id, SlaTimer.status == "armed")
    )
    for timer in timers:
        timer.status = "met"
        timer.fired_at = now
    return TaskView(id=task.id, type=task.type, title=task.title, status=task.status, due_at=task.due_at)


async def patch_priority(session: AsyncSession, actor: Actor, case_id, body: PriorityPatch) -> CaseView:
    if body.priority not in ("normal", "urgent"):
        raise RuleFailed("Priority must be normal or urgent", code="VALIDATION_FAILED", status=400)
    case = await _load_case(session, case_id)
    await assert_case_access(session, actor, case, write=True)
    case.priority = body.priority
    if case.enquiry_id:
        enquiry = await session.get(Enquiry, case.enquiry_id)
        if enquiry and enquiry.status == "new":
            enquiry.priority = body.priority
    return await _case_view(session, case)


async def upsert_party(session: AsyncSession, actor: Actor, case_id, body: PartyBody) -> PartyView:
    assert_staff(actor)
    case = await _load_case(session, case_id)
    await assert_case_access(session, actor, case, write=True)
    if body.role not in ("account_holder", "patient", "companion", "emergency_contact"):
        raise RuleFailed("Unknown party role", code="VALIDATION_FAILED", status=400)
    display = body.display_name
    if body.companion_id:
        companion = await session.get(Companion, body.companion_id)
        if companion is None or companion.customer_id != case.customer_id:
            raise NotFound("Companion not found")
        display = display or companion.display_name
    if not display:
        raise RuleFailed("displayName is required", code="VALIDATION_FAILED", status=400)
    existing = None
    if body.role in ("patient", "account_holder"):
        existing = await session.scalar(
            select(CaseParty).where(CaseParty.case_id == case.id, CaseParty.role == body.role)
        )
    if existing:
        existing.display_name = display
        existing.phone_e164 = body.phone_e164
        existing.date_of_birth = body.date_of_birth
        existing.sex = body.sex
        existing.companion_id = body.companion_id
        existing.is_primary = body.is_primary
        row = existing
    else:
        row = CaseParty(
            case_id=case.id,
            customer_id=case.customer_id if body.role == "account_holder" else None,
            companion_id=body.companion_id,
            role=body.role,
            is_primary=body.is_primary,
            display_name=display,
            phone_e164=body.phone_e164,
            date_of_birth=body.date_of_birth,
            sex=body.sex,
        )
        session.add(row)
        await session.flush()
    return _party_view(row)


async def change_stage(session: AsyncSession, actor: Actor, case_id, body: StageBody) -> CaseView:
    assert_staff(actor)
    case = await _load_case(session, case_id)
    await assert_case_access(session, actor, case, write=True)
    if body.to_stage not in STAGES:
        raise RuleFailed("Unknown stage", code="VALIDATION_FAILED", status=400)
    if case.status == "closed":
        raise RuleFailed("Case is closed", code="RULE_FAILED")
    current = STAGES.index(case.stage)
    target = STAGES.index(body.to_stage)
    if target > current + 1 and not (body.reason and body.reason.strip()):
        raise RuleFailed("Skipping a stage requires a reason", code="VALIDATION_FAILED", status=400)
    previous = case.stage
    case.stage = body.to_stage
    session.add(CaseStageEvent(case_id=case.id, from_stage=previous, to_stage=body.to_stage, reason=body.reason))
    audit(
        session,
        entity_type="case",
        entity_id=case.id,
        action="stage",
        from_status=previous,
        to_status=body.to_stage,
        reason=body.reason,
    )
    return await _case_view(session, case)


async def add_note(session: AsyncSession, actor: Actor, case_id, body: NoteBody) -> NoteView:
    case = await _load_case(session, case_id)
    await assert_case_access(session, actor, case, write=True)
    if body.audience not in ("staff", "patient"):
        raise RuleFailed("Audience must be staff or patient", code="VALIDATION_FAILED", status=400)
    if actor.kind == "customer" and body.audience != "patient":
        raise RuleFailed("Patients can only add patient notes", code="FORBIDDEN", status=403)
    row = CaseNote(case_id=case.id, audience=body.audience, body=body.body)
    session.add(row)
    await session.flush()
    return NoteView(id=row.id, audience=row.audience, body=row.body, at=row.created_at)


async def close_case(session: AsyncSession, actor: Actor, case_id, body: CloseBody) -> CaseView:
    assert_staff(actor)
    case = await _load_case(session, case_id)
    await assert_case_access(session, actor, case, write=True)
    disposition = await session.get(Disposition, body.disposition_code)
    if disposition is None or not disposition.active:
        raise RuleFailed("Unknown disposition", code="VALIDATION_FAILED", status=400)
    if disposition.requires_reason and not (body.reason and body.reason.strip()):
        raise RuleFailed("This disposition requires a reason", code="VALIDATION_FAILED", status=400)
    now = _now()
    case.status = "closed"
    case.closed_at = now
    case.close_disposition = body.disposition_code
    timers = await session.scalars(select(SlaTimer).where(SlaTimer.case_id == case.id, SlaTimer.status == "armed"))
    for timer in timers:
        timer.status = "cancelled"
        timer.fired_at = now
    tasks = await session.scalars(select(Task).where(Task.case_id == case.id, Task.status == "open"))
    for task in tasks:
        task.status = "cancelled"
        task.completed_at = now
    audit(
        session,
        entity_type="case",
        entity_id=case.id,
        action="closed",
        to_status="closed",
        reason=body.reason,
    )
    enqueue(session, "case.closed.v1", {"caseId": str(case.id)})
    return await _case_view(session, case)


async def assign(session: AsyncSession, actor: Actor, case_id, body: AssignmentBody) -> AssignmentView:
    assert_staff(actor)
    case = await _load_case(session, case_id)
    await assert_case_access(session, actor, case, write=True)
    current = await session.scalar(
        select(CaseAssignment).where(
            CaseAssignment.case_id == case.id,
            CaseAssignment.role == body.role,
            CaseAssignment.ended_at.is_(None),
        )
    )
    now = _now()
    if current:
        current.ended_at = now
        current.ended_by = actor.id
    row = CaseAssignment(case_id=case.id, assignee_id=body.assignee_id, role=body.role, assigned_at=now)
    session.add(row)
    await session.flush()
    profile = await session.scalar(select(StaffProfile).where(StaffProfile.user_id == body.assignee_id))
    return AssignmentView(
        id=row.id,
        assignee_id=row.assignee_id,
        role=row.role,
        assigned_at=row.assigned_at,
        ended_at=None,
        display_name=profile.display_name if profile else None,
    )


async def end_assignment(session: AsyncSession, actor: Actor, case_id, assignment_id) -> AssignmentView:
    assert_staff(actor)
    case = await _load_case(session, case_id)
    await assert_case_access(session, actor, case, write=True)
    row = await session.get(CaseAssignment, assignment_id)
    if row is None or row.case_id != case.id:
        raise NotFound("Assignment not found")
    if row.ended_at is None:
        row.ended_at = _now()
        row.ended_by = actor.id
    profile = await session.scalar(select(StaffProfile).where(StaffProfile.user_id == row.assignee_id))
    return AssignmentView(
        id=row.id,
        assignee_id=row.assignee_id,
        role=row.role,
        assigned_at=row.assigned_at,
        ended_at=row.ended_at,
        display_name=profile.display_name if profile else None,
    )


async def get_case(session: AsyncSession, actor: Actor, case_id) -> CaseView:
    case = await _load_case(session, case_id)
    await assert_case_access(session, actor, case, write=False)
    return await _case_view(session, case)


async def my_cases(session: AsyncSession, actor: Actor, cursor: str | None, limit: int | None) -> dict:
    if actor.kind != "customer" or actor.customer_id is None:
        raise RuleFailed("Customer token required", code="FORBIDDEN", status=403)
    size = page(limit)
    offset = decode_offset(cursor)
    rows = list(
        await session.scalars(
            select(Case)
            .where(Case.customer_id == actor.customer_id)
            .order_by(Case.opened_at.desc())
            .offset(offset)
            .limit(size + 1)
        )
    )
    items = [
        CaseSummary(
            id=row.id,
            ref=row.ref,
            stage=row.stage,
            status=row.status,
            priority=row.priority,
            opened_at=row.opened_at,
        )
        for row in rows[:size]
    ]
    next_cursor = encode_offset(offset + size) if len(rows) > size else None
    return {"items": [item.model_dump(mode="json", by_alias=True) for item in items], "nextCursor": next_cursor}


async def journey(session: AsyncSession, actor: Actor, case_id) -> JourneyView:
    case = await _load_case(session, case_id)
    await assert_case_access(session, actor, case, write=False)
    events = await session.scalars(
        select(CaseStageEvent).where(CaseStageEvent.case_id == case.id).order_by(CaseStageEvent.created_at)
    )
    note_query = select(CaseNote).where(CaseNote.case_id == case.id)
    if actor.kind == "customer":
        note_query = note_query.where(CaseNote.audience == "patient")
    notes = await session.scalars(note_query.order_by(CaseNote.created_at))
    return JourneyView(
        events=[
            JourneyEvent(to_stage=row.to_stage, from_stage=row.from_stage, reason=row.reason, at=row.created_at)
            for row in events
        ],
        notes=[NoteView(id=row.id, audience=row.audience, body=row.body, at=row.created_at) for row in notes],
    )


async def list_tasks(session: AsyncSession, actor: Actor, case_id, audience: str | None) -> list[TaskView]:
    case = await _load_case(session, case_id)
    await assert_case_access(session, actor, case, write=False)
    rows = await session.scalars(select(Task).where(Task.case_id == case.id).order_by(Task.due_at))
    views = [TaskView(id=row.id, type=row.type, title=row.title, status=row.status, due_at=row.due_at) for row in rows]
    if audience == "customer" or actor.kind == "customer":
        return [view for view in views if view.type == "handoff_call"]
    return views


async def staff_queue(session: AsyncSession, actor: Actor, *, assignee: str | None, status: str | None, priority: str | None, cursor: str | None, limit: int | None) -> dict:
    assert_staff(actor)
    size = page(limit)
    offset = decode_offset(cursor)
    stmt = select(Case).order_by(Case.opened_at.desc())
    if status:
        stmt = stmt.where(Case.status == status)
    else:
        stmt = stmt.where(Case.status != "closed")
    if priority:
        stmt = stmt.where(Case.priority == priority)
    if assignee == "me":
        stmt = stmt.join(CaseAssignment, CaseAssignment.case_id == Case.id).where(
            CaseAssignment.assignee_id == actor.id,
            CaseAssignment.ended_at.is_(None),
        )
    elif not actor.has_role("ops_admin", "super_admin", "compliance_auditor"):
        stmt = stmt.join(CaseAssignment, CaseAssignment.case_id == Case.id).where(
            CaseAssignment.assignee_id == actor.id,
            CaseAssignment.ended_at.is_(None),
        )
    rows = list(await session.scalars(stmt.offset(offset).limit(size + 1)))
    items = []
    for row in rows[:size]:
        items.append(
            {
                "id": str(row.id),
                "ref": row.ref,
                "stage": row.stage,
                "status": row.status,
                "priority": row.priority,
                "openedAt": row.opened_at.isoformat(),
            }
        )
    return {"items": items, "nextCursor": encode_offset(offset + size) if len(rows) > size else None}


async def sla_breaches(session: AsyncSession, actor: Actor) -> dict:
    assert_staff(actor)
    rows = await session.scalars(select(SlaTimer).where(SlaTimer.status == "fired").order_by(SlaTimer.fired_at.desc()).limit(100))
    return {
        "items": [
            {
                "id": str(row.id),
                "caseId": str(row.case_id),
                "policyKey": row.policy_key,
                "firedAt": row.fired_at.isoformat() if row.fired_at else None,
            }
            for row in rows
        ]
    }


async def list_dispositions(session: AsyncSession, actor: Actor) -> list[dict]:
    assert_staff(actor)
    rows = await session.scalars(select(Disposition).where(Disposition.active.is_(True)))
    return [{"code": row.code, "label": row.label, "requiresReason": row.requires_reason} for row in rows]

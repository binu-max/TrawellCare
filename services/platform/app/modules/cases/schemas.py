from datetime import date, datetime
from uuid import UUID

from app.api_models import APIModel


class TurnIn(APIModel):
    ordinal: int
    role: str
    content: str


class CreateEnquiry(APIModel):
    conversation_id: UUID
    customer_id: UUID
    extracted_slots: dict
    turns: list[TurnIn] = []
    campaign: str | None = None


class EnquiryCreated(APIModel):
    enquiry_id: UUID
    case_id: UUID
    case_ref: str


class EnquiryView(APIModel):
    id: UUID
    conversation_id: UUID
    customer_id: UUID
    case_id: UUID | None
    extracted_slots: dict
    campaign: str | None
    priority: str
    status: str


class TurnView(APIModel):
    ordinal: int
    role: str
    content: str


class ContactAttemptBody(APIModel):
    channel: str
    outcome: str
    notes: str | None = None


class QualificationBody(APIModel):
    outcome: str
    disposition_code: str
    reason: str | None = None


class PriorityPatch(APIModel):
    priority: str


class PartyBody(APIModel):
    role: str
    companion_id: UUID | None = None
    display_name: str | None = None
    phone_e164: str | None = None
    date_of_birth: date | None = None
    sex: str | None = None
    is_primary: bool = False


class PartyView(APIModel):
    id: UUID
    role: str
    display_name: str
    phone_e164: str | None
    date_of_birth: date | None
    sex: str | None
    companion_id: UUID | None
    is_primary: bool


class StageBody(APIModel):
    to_stage: str
    reason: str | None = None


class NoteBody(APIModel):
    audience: str
    body: str


class CloseBody(APIModel):
    disposition_code: str
    reason: str | None = None


class AssignmentBody(APIModel):
    assignee_id: UUID
    role: str


class AssignmentView(APIModel):
    id: UUID
    assignee_id: UUID
    role: str
    assigned_at: datetime
    ended_at: datetime | None
    display_name: str | None = None


class TaskView(APIModel):
    id: UUID
    type: str
    title: str
    status: str
    due_at: datetime | None


class CaseView(APIModel):
    id: UUID
    ref: str
    customer_id: UUID
    stage: str
    status: str
    priority: str
    opened_at: datetime
    closed_at: datetime | None
    parties: list[PartyView]


class CaseSummary(APIModel):
    id: UUID
    ref: str
    stage: str
    status: str
    priority: str
    opened_at: datetime


class Page(APIModel):
    items: list
    next_cursor: str | None = None


class JourneyEvent(APIModel):
    to_stage: str
    from_stage: str | None
    reason: str | None
    at: datetime


class NoteView(APIModel):
    id: UUID
    audience: str
    body: str
    at: datetime


class JourneyView(APIModel):
    events: list[JourneyEvent]
    notes: list[NoteView]


class DispositionView(APIModel):
    code: str
    label: str
    requires_reason: bool

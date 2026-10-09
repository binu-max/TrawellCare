from datetime import date, datetime
from uuid import UUID

from app.api_models import APIModel


class ClinicalProfileBody(APIModel):
    allergies: str | None = None
    medications: str | None = None
    conditions: str | None = None
    prior_procedures: str | None = None


class ClinicalProfileView(ClinicalProfileBody):
    case_id: UUID


class TravelProfileBody(APIModel):
    nationality: str | None = None
    passport_country: str | None = None
    passport_expiry: date | None = None


class TravelProfileView(TravelProfileBody):
    case_party_id: UUID


class ConsultationBody(APIModel):
    doctor_id: UUID
    scheduled_at: datetime
    meeting_link: str | None = None


class RescheduleBody(APIModel):
    scheduled_at: datetime
    meeting_link: str | None = None
    reason: str


class OutcomeBody(APIModel):
    outcome: str
    issue_identified: str | None = None
    clinical_note: str | None = None


class ConsultationView(APIModel):
    id: UUID
    case_id: UUID
    doctor_id: UUID
    scheduled_at: datetime
    meeting_link: str | None
    status: str
    rescheduled_from_id: UUID | None = None
    outcome: str | None = None
    issue_identified: str | None = None
    clinical_note: str | None = None


class ModulePatch(APIModel):
    title: str | None = None
    amount_minor: int | None = None
    price_override_reason: str | None = None
    currency: str | None = None


class CarePlanModuleView(APIModel):
    id: UUID
    module_type: str
    title: str
    currency: str
    amount_minor: int
    tariff_version_id: UUID | None = None


class CarePlanView(APIModel):
    id: UUID
    label: str
    status: str
    selection_reason: str | None
    modules: list[CarePlanModuleView]


class SelectPlan(APIModel):
    selection_reason: str


class MatchRow(APIModel):
    tariff_version_id: UUID
    score: float
    rank: int
    title: str
    amount_minor: int
    currency: str

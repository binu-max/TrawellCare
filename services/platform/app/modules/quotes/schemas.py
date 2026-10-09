from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.api_models import APIModel


class QuoteModuleView(APIModel):
    id: UUID
    module_type: str
    title: str
    description: str
    supplier_name: str | None
    starts_on: date | None
    ends_on: date | None
    quantity: int
    currency: str
    amount_minor: int
    patient_decision: str
    reject_reason: str | None = None


class QuoteView(APIModel):
    id: UUID
    case_id: UUID
    ref: str
    status: str
    version: int
    currency: str
    valid_until: datetime | None
    modules: list[QuoteModuleView]
    total_minor: int


class QuotePatch(APIModel):
    currency: str | None = None
    fx_rate: Decimal | None = None
    fx_base_currency: str | None = None
    valid_until: datetime | None = None


class ModuleEdit(APIModel):
    title: str | None = None
    description: str | None = None
    supplier_name: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    quantity: int | None = None
    amount_minor: int | None = None
    currency: str | None = None
    price_override_reason: str | None = None


class AdjustmentBody(APIModel):
    kind: str
    amount_minor: int
    currency: str
    reason: str


class DecisionBody(APIModel):
    decision: str
    reject_reason: str | None = None


class ChangeRequestBody(APIModel):
    module_id: UUID
    reason: str


class SignoffBody(APIModel):
    version: int
    otp_challenge_id: UUID
    consent_accepted: bool


class SignoffResult(APIModel):
    booking_ref: str
    signoff_id: UUID
    booking_id: UUID


class ItineraryBody(APIModel):
    kind: str
    title: str
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: str | None = None
    service_line_id: UUID | None = None
    sort_order: int = 0


class ServiceLineEventBody(APIModel):
    status: str
    supplier_reference: str | None = None
    note: str | None = None
    manual_confirmation: bool = False


class DocumentBody(APIModel):
    code: str
    case_party_id: UUID | None = None


class DocumentPatch(APIModel):
    status: str
    vault_document_id: UUID | None = None


class CancellationBody(APIModel):
    reason: str


class DecisionResult(APIModel):
    status: str

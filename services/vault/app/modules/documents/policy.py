from uuid import UUID

from tc_common import Forbidden, ValidationFailed
from tc_common.jwt import TokenActor

FINANCE = {"finance_maker", "finance_checker"}
ALLOWED_CLASSIFICATIONS = {
    "passport",
    "medical_report",
    "visa",
    "other",
    "signoff_pdf",
    "travel_ticket",
    "hospital_letter",
}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/heic",
    "image/heif",
}


def assert_not_finance(actor: TokenActor) -> None:
    if actor.has_role(*FINANCE):
        raise Forbidden("Finance cannot access the vault")


def assert_classification(code: str) -> None:
    if code not in ALLOWED_CLASSIFICATIONS:
        raise ValidationFailed("Unknown document classification")


def assert_content_type(content_type: str) -> None:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationFailed("Content type is not allowed")


def assert_customer_case(actor: TokenActor, case_customer_id: UUID) -> None:
    if actor.kind != "customer" or actor.customer_id is None:
        raise Forbidden("Customer token required")
    if actor.customer_id != case_customer_id:
        raise Forbidden("Case not found")


def assert_staff(actor: TokenActor) -> None:
    if actor.kind != "staff":
        raise Forbidden("Staff token required")


def can_view_document(actor: TokenActor, *, customer_id: UUID | None, visible_to_customer: bool) -> None:
    assert_not_finance(actor)
    if actor.kind == "customer":
        if not visible_to_customer:
            raise Forbidden("Document not found")
        if customer_id is None or actor.customer_id != customer_id:
            raise Forbidden("Document not found")
    elif actor.kind == "staff":
        return
    else:
        raise Forbidden("Invalid token")

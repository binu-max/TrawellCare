from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tc_common import Forbidden, NotFound, RuleFailed

from app.access import assert_case_access, assert_staff
from app.actor import Actor
from app.events import audit, enqueue
from app.modules.cases.models import Case, CaseParty, SlaTimer
from app.modules.clinical.models import CarePlan, CarePlanModule, TravelProfile
from app.modules.control.models import ConsentText
from app.modules.engagement.models import FollowUp, PointsEvent
from app.modules.identity.models import Customer, OtpChallenge, PhoneIdentity, User
from app.modules.quotes.models import (
    Booking,
    CancellationRequest,
    DocumentRequirement,
    ItineraryItem,
    Quote,
    QuoteAdjustment,
    QuoteChangeRequest,
    QuoteModule,
    QuoteVersion,
    ServiceLine,
    ServiceLineEvent,
    Signoff,
)
from app.modules.quotes.schemas import (
    AdjustmentBody,
    CancellationBody,
    ChangeRequestBody,
    DecisionBody,
    DocumentBody,
    DocumentPatch,
    ItineraryBody,
    ModuleEdit,
    QuoteModuleView,
    QuotePatch,
    QuoteView,
    ServiceLineEventBody,
    SignoffBody,
    SignoffResult,
)
from app.refs import next_ref

LINE_STATUSES = {
    "not_required",
    "requested",
    "quoted",
    "confirmed",
    "scheduled",
    "in_progress",
    "completed",
    "exception",
    "cancelled",
    "refunded",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _display_amount(amount: int, currency: str, version: QuoteVersion) -> int:
    if currency == version.currency:
        return amount
    if currency == version.fx_base_currency:
        return int(round(amount * float(version.fx_rate)))
    raise RuleFailed("No FX rate for module currency", code="FX_MISSING")


async def _case(session: AsyncSession, case_id) -> Case:
    row = await session.get(Case, case_id)
    if row is None:
        raise NotFound("Case not found")
    return row


async def _quote(session: AsyncSession, quote_id, *, lock: bool = False) -> Quote:
    stmt = select(Quote).where(Quote.id == quote_id)
    if lock:
        stmt = stmt.with_for_update()
    row = await session.scalar(stmt)
    if row is None:
        raise NotFound("Quote not found")
    return row


async def _version(session: AsyncSession, quote: Quote) -> QuoteVersion:
    row = await session.scalar(
        select(QuoteVersion).where(QuoteVersion.quote_id == quote.id, QuoteVersion.version == quote.current_version)
    )
    if row is None:
        raise NotFound("Quote version not found")
    return row


async def _modules(session: AsyncSession, version_id) -> list[QuoteModule]:
    rows = await session.scalars(select(QuoteModule).where(QuoteModule.quote_version_id == version_id))
    return list(rows)


async def _adjustments(session: AsyncSession, version_id) -> list[QuoteAdjustment]:
    rows = await session.scalars(select(QuoteAdjustment).where(QuoteAdjustment.quote_version_id == version_id))
    return list(rows)


def _total(modules: list[QuoteModule], adjustments: list[QuoteAdjustment], version: QuoteVersion, *, accepted_only: bool) -> int:
    chosen = [row for row in modules if row.patient_decision == "accepted"] if accepted_only else modules
    total = sum(_display_amount(row.amount_minor * row.quantity, row.currency, version) for row in chosen)
    for adjustment in adjustments:
        signed = adjustment.amount_minor if adjustment.kind == "surcharge" else -adjustment.amount_minor
        total += _display_amount(signed, adjustment.currency, version)
    return total


def _module_view(row: QuoteModule) -> QuoteModuleView:
    return QuoteModuleView(
        id=row.id,
        module_type=row.module_type,
        title=row.title,
        description=row.description,
        supplier_name=row.supplier_name,
        starts_on=row.starts_on,
        ends_on=row.ends_on,
        quantity=row.quantity,
        currency=row.currency,
        amount_minor=row.amount_minor,
        patient_decision=row.patient_decision,
        reject_reason=row.reject_reason,
    )


async def _view(session: AsyncSession, quote: Quote, *, customer: bool) -> QuoteView:
    version = await _version(session, quote)
    modules = await _modules(session, version.id)
    adjustments = await _adjustments(session, version.id)
    if customer and quote.status == "draft":
        raise NotFound("Quote not found")
    return QuoteView(
        id=quote.id,
        case_id=quote.case_id,
        ref=quote.ref,
        status=quote.status,
        version=quote.current_version,
        currency=version.currency,
        valid_until=version.valid_until,
        modules=[_module_view(row) for row in modules],
        total_minor=_total(modules, adjustments, version, accepted_only=False),
    )


async def materialize_quote(session: AsyncSession, case: Case, plan: CarePlan) -> dict:
    existing = await session.scalar(select(Quote).where(Quote.case_id == case.id, Quote.care_plan_id == plan.id))
    if existing:
        return {"quoteId": str(existing.id), "quoteRef": existing.ref, "status": existing.status}
    plan_modules = list(await session.scalars(select(CarePlanModule).where(CarePlanModule.care_plan_id == plan.id)))
    currency = plan_modules[0].currency if plan_modules else "OMR"
    quote = Quote(case_id=case.id, care_plan_id=plan.id, ref=await next_ref(session, "quote"), status="draft", current_version=1)
    session.add(quote)
    await session.flush()
    version = QuoteVersion(
        quote_id=quote.id,
        version=1,
        status="draft",
        currency=currency,
        fx_rate=Decimal("1"),
        fx_base_currency=currency,
    )
    session.add(version)
    await session.flush()
    for module in plan_modules:
        session.add(
            QuoteModule(
                quote_version_id=version.id,
                module_type=module.module_type,
                title=module.title,
                currency=module.currency,
                amount_minor=module.amount_minor,
                tariff_version_id=module.tariff_version_id,
            )
        )
    audit(session, entity_type="quote", entity_id=quote.id, action="drafted", to_status="draft")
    return {"quoteId": str(quote.id), "quoteRef": quote.ref, "status": quote.status}


async def create_quote(session: AsyncSession, actor: Actor, case_id) -> QuoteView:
    assert_staff(actor)
    case = await _case(session, case_id)
    await assert_case_access(session, actor, case, write=True)
    plan = await session.scalar(select(CarePlan).where(CarePlan.case_id == case.id, CarePlan.status == "selected"))
    if plan is None:
        raise RuleFailed("Select a care plan before creating a quote", code="RULE_FAILED")
    await materialize_quote(session, case, plan)
    quote = await session.scalar(select(Quote).where(Quote.case_id == case.id, Quote.care_plan_id == plan.id))
    return await _view(session, quote, customer=False)


async def list_quotes(session: AsyncSession, actor: Actor, case_id, visibility: str | None) -> list[QuoteView]:
    case = await _case(session, case_id)
    await assert_case_access(session, actor, case, write=False)
    customer = actor.kind == "customer" or visibility == "customer"
    rows = await session.scalars(select(Quote).where(Quote.case_id == case.id).order_by(Quote.created_at))
    views = []
    for row in rows:
        if customer and row.status == "draft":
            continue
        views.append(await _view(session, row, customer=customer))
    return views


async def get_quote(session: AsyncSession, actor: Actor, quote_id) -> QuoteView:
    quote = await _quote(session, quote_id)
    case = await _case(session, quote.case_id)
    await assert_case_access(session, actor, case, write=False)
    return await _view(session, quote, customer=actor.kind == "customer")


async def patch_quote(session: AsyncSession, actor: Actor, quote_id, body: QuotePatch) -> QuoteView:
    assert_staff(actor)
    quote = await _quote(session, quote_id)
    if quote.status != "draft":
        raise RuleFailed("Only a draft quote can be edited", code="CONFLICT", status=409)
    case = await _case(session, quote.case_id)
    await assert_case_access(session, actor, case, write=True)
    version = await _version(session, quote)
    if body.currency:
        version.currency = body.currency.upper()
    if body.fx_rate is not None:
        version.fx_rate = body.fx_rate
        version.fx_as_of = _now()
    if body.fx_base_currency:
        version.fx_base_currency = body.fx_base_currency.upper()
    if body.valid_until:
        version.valid_until = body.valid_until
    return await _view(session, quote, customer=False)


async def patch_module(session: AsyncSession, actor: Actor, quote_id, module_id, body: ModuleEdit) -> QuoteModuleView:
    assert_staff(actor)
    quote = await _quote(session, quote_id)
    if quote.status != "draft":
        raise RuleFailed("Only a draft quote can be edited", code="CONFLICT", status=409)
    case = await _case(session, quote.case_id)
    await assert_case_access(session, actor, case, write=True)
    version = await _version(session, quote)
    module = await session.get(QuoteModule, module_id)
    if module is None or module.quote_version_id != version.id:
        raise NotFound("Module not found")
    if body.amount_minor is not None and body.amount_minor != module.amount_minor and not body.price_override_reason:
        raise RuleFailed("A price change requires a reason", code="VALIDATION_FAILED", status=400)
    for field in ("title", "description", "supplier_name", "starts_on", "ends_on", "quantity"):
        value = getattr(body, field)
        if value is not None:
            setattr(module, field, value)
    if body.amount_minor is not None:
        module.amount_minor = body.amount_minor
        module.price_override_reason = body.price_override_reason
    if body.currency:
        module.currency = body.currency.upper()
    return _module_view(module)


async def add_adjustment(session: AsyncSession, actor: Actor, quote_id, body: AdjustmentBody) -> QuoteView:
    assert_staff(actor)
    if body.kind not in ("discount", "surcharge"):
        raise RuleFailed("kind must be discount or surcharge", code="VALIDATION_FAILED", status=400)
    if not body.reason.strip():
        raise RuleFailed("reason is required", code="VALIDATION_FAILED", status=400)
    quote = await _quote(session, quote_id)
    if quote.status != "draft":
        raise RuleFailed("Only a draft quote can be edited", code="CONFLICT", status=409)
    case = await _case(session, quote.case_id)
    await assert_case_access(session, actor, case, write=True)
    version = await _version(session, quote)
    session.add(
        QuoteAdjustment(
            quote_version_id=version.id,
            kind=body.kind,
            amount_minor=body.amount_minor,
            currency=body.currency.upper(),
            reason=body.reason,
        )
    )
    return await _view(session, quote, customer=False)


async def _passport_blocks(session: AsyncSession, case_id, modules: list[QuoteModule]) -> None:
    ends = [module.ends_on for module in modules if module.ends_on]
    if not ends:
        return
    latest = max(ends)
    parties = await session.scalars(select(CaseParty).where(CaseParty.case_id == case_id))
    for party in parties:
        profile = await session.scalar(select(TravelProfile).where(TravelProfile.case_party_id == party.id))
        if profile and profile.passport_expiry and profile.passport_expiry < latest:
            raise RuleFailed("A passport expires before the trip ends", code="PASSPORT_EXPIRES")


async def publish_quote(session: AsyncSession, actor: Actor, quote_id) -> QuoteView:
    assert_staff(actor)
    quote = await _quote(session, quote_id, lock=True)
    if quote.status != "draft":
        raise RuleFailed("Only a draft quote can be published", code="CONFLICT", status=409)
    case = await _case(session, quote.case_id)
    await assert_case_access(session, actor, case, write=True)
    version = await _version(session, quote)
    modules = await _modules(session, version.id)
    await _passport_blocks(session, case.id, modules)
    if version.valid_until is None:
        version.valid_until = _now() + timedelta(days=14)
    quote.status = "published"
    version.status = "published"
    audit(session, entity_type="quote", entity_id=quote.id, action="published", from_status="draft", to_status="published")
    enqueue(session, "quote.published.v1", {"caseId": str(case.id), "quoteId": str(quote.id)})
    return await _view(session, quote, customer=False)


async def decide(session: AsyncSession, actor: Actor, quote_id, module_id, body: DecisionBody) -> QuoteModuleView:
    if actor.kind != "customer":
        raise Forbidden("Only the patient can decide a module")
    if body.decision not in ("accept", "reject"):
        raise RuleFailed("decision must be accept or reject", code="VALIDATION_FAILED", status=400)
    if body.decision == "reject" and not (body.reject_reason and body.reject_reason.strip()):
        raise RuleFailed("rejectReason is required", code="VALIDATION_FAILED", status=400)
    quote = await _quote(session, quote_id, lock=True)
    if quote.status != "published":
        raise RuleFailed("Quote is not open for decisions", code="CONFLICT", status=409)
    case = await _case(session, quote.case_id)
    await assert_case_access(session, actor, case, write=False)
    version = await _version(session, quote)
    module = await session.get(QuoteModule, module_id)
    if module is None or module.quote_version_id != version.id:
        raise NotFound("Module not found")
    module.patient_decision = "accepted" if body.decision == "accept" else "rejected"
    module.reject_reason = body.reject_reason
    module.decided_at = _now()
    return _module_view(module)


async def change_request(session: AsyncSession, actor: Actor, quote_id, body: ChangeRequestBody) -> QuoteView:
    quote = await _quote(session, quote_id, lock=True)
    if quote.status != "published":
        raise RuleFailed("Change requests apply to a published quote", code="CONFLICT", status=409)
    case = await _case(session, quote.case_id)
    await assert_case_access(session, actor, case, write=actor.kind != "customer")
    version = await _version(session, quote)
    module = await session.get(QuoteModule, body.module_id)
    if module is None or module.quote_version_id != version.id:
        raise NotFound("Module not found")
    if module.patient_decision != "rejected":
        raise RuleFailed("Only a rejected module can be changed", code="RULE_FAILED")
    modules = await _modules(session, version.id)
    adjustments = await _adjustments(session, version.id)
    version.status = "superseded"
    next_version = quote.current_version + 1
    created = QuoteVersion(
        quote_id=quote.id,
        version=next_version,
        status="draft",
        currency=version.currency,
        valid_until=None,
        fx_rate=version.fx_rate,
        fx_base_currency=version.fx_base_currency,
        fx_as_of=version.fx_as_of,
    )
    session.add(created)
    await session.flush()
    for source in modules:
        session.add(
            QuoteModule(
                quote_version_id=created.id,
                module_type=source.module_type,
                title=source.title,
                description=source.description,
                supplier_name=source.supplier_name,
                starts_on=source.starts_on,
                ends_on=source.ends_on,
                quantity=source.quantity,
                currency=source.currency,
                amount_minor=source.amount_minor,
                price_override_reason=source.price_override_reason,
                tariff_version_id=source.tariff_version_id,
                patient_decision="pending" if source.id == module.id else source.patient_decision,
                reject_reason=None if source.id == module.id else source.reject_reason,
            )
        )
    for source in adjustments:
        session.add(
            QuoteAdjustment(
                quote_version_id=created.id,
                kind=source.kind,
                amount_minor=source.amount_minor,
                currency=source.currency,
                reason=source.reason,
            )
        )
    quote.current_version = next_version
    quote.status = "draft"
    session.add(
        QuoteChangeRequest(
            quote_id=quote.id,
            from_version=version.version,
            to_version=next_version,
            module_id=module.id,
            reason=body.reason,
        )
    )
    enqueue(
        session,
        "quote.change_requested.v1",
        {"caseId": str(case.id), "quoteId": str(quote.id), "version": next_version},
    )
    return await _view(session, quote, customer=False)


async def signoff(
    session: AsyncSession,
    actor: Actor,
    quote_id,
    body: SignoffBody,
    *,
    ip: str | None,
    user_agent: str | None,
) -> SignoffResult:
    if actor.kind != "customer" or not body.consent_accepted:
        raise RuleFailed("Consent is required", code="VALIDATION_FAILED", status=400)
    quote = await _quote(session, quote_id, lock=True)
    if quote.status != "published":
        raise RuleFailed("Quote cannot be signed", code="CONFLICT", status=409)
    if body.version != quote.current_version:
        raise RuleFailed("Quote version does not match", code="QUOTE_VERSION_MISMATCH")
    case = await _case(session, quote.case_id)
    await assert_case_access(session, actor, case, write=False)
    version = await _version(session, quote)
    if version.valid_until and version.valid_until < _now():
        quote.status = "expired"
        raise RuleFailed("Quote has expired", code="QUOTE_EXPIRED")
    modules = await _modules(session, version.id)
    if any(module.patient_decision == "pending" for module in modules):
        raise RuleFailed("Every module needs a decision", code="MODULE_NOT_DECIDED")
    if any(module.patient_decision == "rejected" for module in modules):
        raise RuleFailed("A rejected module needs a change request", code="QUOTE_HAS_REJECTION")
    accepted = [module for module in modules if module.patient_decision == "accepted"]
    if not accepted:
        raise RuleFailed("At least one module must be accepted", code="NOTHING_ACCEPTED")
    challenge = await session.get(OtpChallenge, body.otp_challenge_id)
    if (
        challenge is None
        or challenge.purpose != "signoff"
        or challenge.verified_at is None
        or challenge.consumed_at is not None
        or challenge.expires_at < _now()
    ):
        raise RuleFailed("A fresh sign-off code is required", code="OTP_EXPIRED")
    identity = await session.scalar(
        select(PhoneIdentity).where(PhoneIdentity.user_id == actor.id, PhoneIdentity.phone_hash == challenge.phone_hash)
    )
    if identity is None:
        raise RuleFailed("A fresh sign-off code is required", code="OTP_EXPIRED")
    consent = await session.scalar(
        select(ConsentText).where(ConsentText.purpose == "quote_signoff", ConsentText.active.is_(True))
    )
    if consent is None:
        raise RuleFailed("Sign-off consent text is not configured", code="RULE_FAILED")
    adjustments = await _adjustments(session, version.id)
    total = _total(modules, adjustments, version, accepted_only=True)
    if total < 0:
        raise RuleFailed("Quote total cannot be negative", code="ALLOCATION_MISMATCH")
    now = _now()
    challenge.consumed_at = now
    evidence = Signoff(
        quote_version_id=version.id,
        customer_id=actor.customer_id,
        consent_text_version=str(consent.version),
        otp_challenge_id=challenge.id,
        ip=ip,
        user_agent=user_agent,
        signed_at=now,
    )
    session.add(evidence)
    quote.status = "accepted"
    version.status = "accepted"
    booking = Booking(
        case_id=case.id,
        quote_id=quote.id,
        ref=await next_ref(session, "booking"),
        currency=version.currency,
        amount_minor=total,
        payment_state="unknown",
    )
    session.add(booking)
    await session.flush()
    for module in accepted:
        session.add(
            ServiceLine(
                booking_id=booking.id,
                quote_module_id=module.id,
                module_type=module.module_type,
                title=module.title,
                status="requested",
                currency=module.currency,
                amount_minor=module.amount_minor,
            )
        )
    customer = await session.get(Customer, actor.customer_id)
    if customer:
        session.add(
            PointsEvent(
                customer_id=customer.id,
                case_id=case.id,
                points=100,
                reason="quote_accepted",
                expires_at=now + timedelta(days=365),
            )
        )
    audit(session, entity_type="quote", entity_id=quote.id, action="accepted", from_status="published", to_status="accepted")
    enqueue(
        session,
        "quote.accepted.v1",
        {
            "caseId": str(case.id),
            "bookingId": str(booking.id),
            "quoteId": str(quote.id),
            "version": quote.current_version,
            "amountMinor": total,
            "currency": version.currency,
            "customerId": str(actor.customer_id),
        },
    )
    await session.flush()
    return SignoffResult(booking_ref=booking.ref, signoff_id=evidence.id, booking_id=booking.id)


async def decline_quote(session: AsyncSession, actor: Actor, quote_id) -> QuoteView:
    quote = await _quote(session, quote_id, lock=True)
    case = await _case(session, quote.case_id)
    await assert_case_access(session, actor, case, write=actor.kind != "customer")
    if quote.status != "published":
        raise RuleFailed("Only a published quote can be declined", code="CONFLICT", status=409)
    quote.status = "declined"
    audit(session, entity_type="quote", entity_id=quote.id, action="declined", to_status="declined")
    return await _view(session, quote, customer=actor.kind == "customer")


async def commercial_summary(session: AsyncSession, actor: Actor, booking_id) -> dict:
    booking = await session.get(Booking, booking_id)
    if booking is None:
        raise NotFound("Booking not found")
    case = await _case(session, booking.case_id)
    await assert_case_access(session, actor, case, write=False)
    customer = await session.get(Customer, case.customer_id)
    user = await session.get(User, customer.user_id) if customer else None
    return {
        "bookingId": str(booking.id),
        "bookingRef": booking.ref,
        "amountMinor": booking.amount_minor,
        "currency": booking.currency,
        "email": user.email if user else None,
        "paymentState": booking.payment_state,
    }


async def add_itinerary(session: AsyncSession, actor: Actor, case_id, body: ItineraryBody) -> dict:
    assert_staff(actor)
    case = await _case(session, case_id)
    await assert_case_access(session, actor, case, write=True)
    row = ItineraryItem(
        case_id=case.id,
        service_line_id=body.service_line_id,
        kind=body.kind,
        title=body.title,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        location=body.location,
        sort_order=body.sort_order,
    )
    session.add(row)
    await session.flush()
    return {"id": str(row.id), "title": row.title}


async def list_itinerary(session: AsyncSession, actor: Actor, case_id) -> list[dict]:
    case = await _case(session, case_id)
    await assert_case_access(session, actor, case, write=False)
    rows = await session.scalars(
        select(ItineraryItem).where(ItineraryItem.case_id == case.id).order_by(ItineraryItem.sort_order)
    )
    return [
        {
            "id": str(row.id),
            "kind": row.kind,
            "title": row.title,
            "startsAt": row.starts_at.isoformat() if row.starts_at else None,
            "endsAt": row.ends_at.isoformat() if row.ends_at else None,
            "location": row.location,
        }
        for row in rows
    ]


async def add_service_event(session: AsyncSession, actor: Actor, line_id, body: ServiceLineEventBody) -> dict:
    assert_staff(actor)
    if body.status not in LINE_STATUSES:
        raise RuleFailed("Unknown service line status", code="VALIDATION_FAILED", status=400)
    if body.status == "confirmed" and not body.supplier_reference and not body.manual_confirmation:
        raise RuleFailed("Confirmed lines need a supplier reference or a manual confirmation", code="VALIDATION_FAILED", status=400)
    line = await session.get(ServiceLine, line_id)
    if line is None:
        raise NotFound("Service line not found")
    booking = await session.get(Booking, line.booking_id)
    case = await _case(session, booking.case_id)
    await assert_case_access(session, actor, case, write=True)
    line.status = body.status
    session.add(
        ServiceLineEvent(
            service_line_id=line.id,
            status=body.status,
            supplier_reference=body.supplier_reference,
            note=body.note,
            manual_confirmation=body.manual_confirmation,
        )
    )
    if body.status == "completed" and line.module_type == "hospital":
        await _arm_followup(session, case)
    return {"status": line.status}


async def _arm_followup(session: AsyncSession, case: Case) -> None:
    from app.modules.control.models import SlaPolicy

    existing = await session.scalar(select(FollowUp).where(FollowUp.case_id == case.id, FollowUp.completed_at.is_(None)))
    if existing:
        return
    policy = await session.get(SlaPolicy, "followup")
    seconds = policy.duration_seconds if policy else 30 * 24 * 3600
    event_type = policy.event_type if policy else "followup.due.v1"
    due = _now() + timedelta(seconds=seconds)
    follow = FollowUp(case_id=case.id, due_at=due)
    session.add(follow)
    await session.flush()
    session.add(
        SlaTimer(
            case_id=case.id,
            policy_key="followup",
            due_at=due,
            status="armed",
            event_type=event_type,
        )
    )


async def add_document(session: AsyncSession, actor: Actor, case_id, body: DocumentBody) -> dict:
    assert_staff(actor)
    case = await _case(session, case_id)
    await assert_case_access(session, actor, case, write=True)
    if body.code not in ("passport", "medical_report", "visa", "other"):
        raise RuleFailed("Unknown document code", code="VALIDATION_FAILED", status=400)
    row = DocumentRequirement(case_id=case.id, case_party_id=body.case_party_id, code=body.code, status="missing")
    session.add(row)
    await session.flush()
    return {"id": str(row.id), "code": row.code, "status": row.status}


async def patch_document(session: AsyncSession, actor: Actor, case_id, requirement_id, body: DocumentPatch) -> dict:
    case = await _case(session, case_id)
    await assert_case_access(session, actor, case, write=actor.kind != "customer")
    row = await session.get(DocumentRequirement, requirement_id)
    if row is None or row.case_id != case.id:
        raise NotFound("Document requirement not found")
    if actor.kind == "customer" and body.status != "uploaded":
        raise Forbidden("Patients can mark a document uploaded")
    if body.status not in ("missing", "uploaded", "accepted", "rejected"):
        raise RuleFailed("Unknown document status", code="VALIDATION_FAILED", status=400)
    row.status = body.status
    if body.vault_document_id:
        row.vault_document_id = body.vault_document_id
    return {"id": str(row.id), "status": row.status}


async def list_documents(session: AsyncSession, actor: Actor, case_id) -> list[dict]:
    case = await _case(session, case_id)
    await assert_case_access(session, actor, case, write=False)
    rows = await session.scalars(select(DocumentRequirement).where(DocumentRequirement.case_id == case.id))
    return [
        {
            "id": str(row.id),
            "code": row.code,
            "status": row.status,
            "casePartyId": str(row.case_party_id) if row.case_party_id else None,
            "vaultDocumentId": str(row.vault_document_id) if row.vault_document_id else None,
        }
        for row in rows
    ]


async def request_cancellation(session: AsyncSession, actor: Actor, booking_id, body: CancellationBody) -> dict:
    booking = await session.get(Booking, booking_id)
    if booking is None:
        raise NotFound("Booking not found")
    case = await _case(session, booking.case_id)
    await assert_case_access(session, actor, case, write=actor.kind != "customer")
    row = CancellationRequest(booking_id=booking.id, reason=body.reason, status="requested")
    session.add(row)
    await session.flush()
    return {"id": str(row.id), "status": row.status}


async def decide_cancellation(session: AsyncSession, actor: Actor, request_id, approved: bool) -> dict:
    assert_staff(actor)
    row = await session.get(CancellationRequest, request_id)
    if row is None:
        raise NotFound("Cancellation request not found")
    booking = await session.get(Booking, row.booking_id)
    case = await _case(session, booking.case_id)
    await assert_case_access(session, actor, case, write=True)
    row.status = "approved" if approved else "rejected"
    row.decided_by = actor.id
    if approved:
        lines = await session.scalars(select(ServiceLine).where(ServiceLine.booking_id == booking.id))
        for line in lines:
            line.status = "cancelled"
            session.add(ServiceLineEvent(service_line_id=line.id, status="cancelled", note="cancellation approved"))
    return {"id": str(row.id), "status": row.status}

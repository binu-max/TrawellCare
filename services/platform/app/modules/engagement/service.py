import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tc_common import Conflict, NotFound, RuleFailed

from app.access import assert_case_access, assert_staff
from app.actor import Actor
from app.modules.cases.models import Case, Enquiry, Qualification, SlaTimer
from app.modules.engagement.models import FollowUp, PointsEvent, Referral, Review
from app.modules.quotes.models import Booking, Quote


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _case(session: AsyncSession, case_id) -> Case:
    row = await session.get(Case, case_id)
    if row is None:
        raise NotFound("Case not found")
    return row


async def add_review(session: AsyncSession, actor: Actor, case_id, rating: int, body: str) -> dict:
    if actor.kind != "customer":
        raise RuleFailed("Only a customer can review", code="FORBIDDEN", status=403)
    if rating < 1 or rating > 5:
        raise RuleFailed("Rating must be from 1 to 5", code="VALIDATION_FAILED", status=400)
    case = await _case(session, case_id)
    await assert_case_access(session, actor, case, write=False)
    existing = await session.scalar(select(Review).where(Review.case_id == case.id, Review.customer_id == actor.customer_id))
    if existing:
        raise Conflict("A review already exists for this case")
    row = Review(case_id=case.id, customer_id=actor.customer_id, rating=rating, body=body, status="pending")
    session.add(row)
    await session.flush()
    return {"id": str(row.id), "status": row.status}


async def moderate_review(session: AsyncSession, actor: Actor, review_id, status: str) -> dict:
    assert_staff(actor)
    if status not in ("published", "rejected"):
        raise RuleFailed("Status must be published or rejected", code="VALIDATION_FAILED", status=400)
    row = await session.get(Review, review_id)
    if row is None:
        raise NotFound("Review not found")
    row.status = status
    return {"id": str(row.id), "status": row.status}


async def create_referral(session: AsyncSession, actor: Actor) -> dict:
    if actor.customer_id is None:
        raise RuleFailed("Customer token required", code="FORBIDDEN", status=403)
    code = secrets.token_hex(4)
    row = Referral(code=code, referrer_customer_id=actor.customer_id, status="open")
    session.add(row)
    await session.flush()
    return {"code": row.code}


async def points_balance(session: AsyncSession, actor: Actor) -> dict:
    if actor.customer_id is None:
        raise RuleFailed("Customer token required", code="FORBIDDEN", status=403)
    now = _now()
    total = await session.scalar(
        select(func.coalesce(func.sum(PointsEvent.points), 0)).where(
            PointsEvent.customer_id == actor.customer_id,
            (PointsEvent.expires_at.is_(None)) | (PointsEvent.expires_at > now),
        )
    )
    return {"points": int(total or 0)}


async def open_followup(session: AsyncSession, actor: Actor, case_id) -> dict:
    assert_staff(actor)
    case = await _case(session, case_id)
    await assert_case_access(session, actor, case, write=True)
    from app.modules.quotes.service import _arm_followup

    await _arm_followup(session, case)
    row = await session.scalar(select(FollowUp).where(FollowUp.case_id == case.id, FollowUp.completed_at.is_(None)))
    return {"id": str(row.id), "dueAt": row.due_at.isoformat()}


async def complete_followup(session: AsyncSession, actor: Actor, follow_id, outcome: str, notes: str | None) -> dict:
    assert_staff(actor)
    row = await session.get(FollowUp, follow_id)
    if row is None:
        raise NotFound("Follow-up not found")
    case = await _case(session, row.case_id)
    await assert_case_access(session, actor, case, write=True)
    row.completed_at = _now()
    row.outcome = outcome
    row.notes = notes
    timers = await session.scalars(
        select(SlaTimer).where(SlaTimer.case_id == case.id, SlaTimer.policy_key == "followup", SlaTimer.status == "armed")
    )
    for timer in timers:
        timer.status = "met"
        timer.fired_at = row.completed_at
    return {"id": str(row.id), "outcome": row.outcome}


async def report_funnel(session: AsyncSession, actor: Actor) -> dict:
    assert_staff(actor)
    enquiries = await session.execute(select(Enquiry.status, func.count()).group_by(Enquiry.status))
    quotes = await session.execute(select(Quote.status, func.count()).group_by(Quote.status))
    return {
        "enquiries": {status: count for status, count in enquiries},
        "quotes": {status: count for status, count in quotes},
    }


async def report_sla(session: AsyncSession, actor: Actor) -> dict:
    assert_staff(actor)
    rows = await session.execute(select(SlaTimer.status, func.count()).group_by(SlaTimer.status))
    return {"timers": {status: count for status, count in rows}}


async def report_qualification(session: AsyncSession, actor: Actor) -> dict:
    assert_staff(actor)
    rows = await session.execute(select(Qualification.disposition_code, func.count()).group_by(Qualification.disposition_code))
    return {"dispositions": {code: count for code, count in rows}}


async def apply_payment(session: AsyncSession, event_id, event_type: str, payload: dict) -> dict:
    from app.modules.control.models import Inbox

    existing = await session.get(Inbox, event_id)
    if existing:
        return {"status": "duplicate"}
    booking_id = payload.get("bookingId")
    booking = await session.get(Booking, booking_id) if booking_id else None
    if booking and event_type == "payment.succeeded.v1":
        booking.payment_state = "succeeded"
    elif booking and event_type == "payment.failed.v1":
        booking.payment_state = "failed"
    session.add(Inbox(event_id=event_id, type=event_type))
    return {"status": "applied"}

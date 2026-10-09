from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api_models import APIModel
from app.deps import CustomerDep, ServiceDep, SessionDep, StaffDep
from app.modules.engagement import service


class ReviewBody(APIModel):
    rating: int
    body: str = ""


class ModerateBody(APIModel):
    status: str


class FollowUpBody(APIModel):
    outcome: str
    notes: str | None = None


class InboxBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    event_id: UUID = Field(alias="eventId")
    event_type: str = Field(alias="type")
    payload: dict = {}


router = APIRouter(tags=["engagement"])


@router.post("/v1/cases/{case_id}/reviews", status_code=201)
async def review(case_id: UUID, body: ReviewBody, actor: CustomerDep, session: SessionDep):
    return await service.add_review(session, actor, case_id, body.rating, body.body)


@router.post("/v1/reviews/{review_id}/moderate")
async def moderate(review_id: UUID, body: ModerateBody, actor: StaffDep, session: SessionDep):
    return await service.moderate_review(session, actor, review_id, body.status)


@router.post("/v1/customers/me/referrals", status_code=201)
async def referral(actor: CustomerDep, session: SessionDep):
    return await service.create_referral(session, actor)


@router.get("/v1/customers/me/points")
async def points(actor: CustomerDep, session: SessionDep):
    return await service.points_balance(session, actor)


@router.post("/v1/cases/{case_id}/follow-ups", status_code=201)
async def open_followup(case_id: UUID, actor: StaffDep, session: SessionDep):
    return await service.open_followup(session, actor, case_id)


@router.post("/v1/follow-ups/{follow_id}/complete")
async def complete_followup(follow_id: UUID, body: FollowUpBody, actor: StaffDep, session: SessionDep):
    return await service.complete_followup(session, actor, follow_id, body.outcome, body.notes)


@router.get("/v1/reports/funnel")
async def funnel(actor: StaffDep, session: SessionDep):
    return await service.report_funnel(session, actor)


@router.get("/v1/reports/sla")
async def sla(actor: StaffDep, session: SessionDep):
    return await service.report_sla(session, actor)


@router.get("/v1/reports/qualification")
async def qualification(actor: StaffDep, session: SessionDep):
    return await service.report_qualification(session, actor)


@router.post("/v1/internal/events")
async def inbox(body: InboxBody, actor: ServiceDep, session: SessionDep):
    del actor
    return await service.apply_payment(session, body.event_id, body.event_type, body.payload)

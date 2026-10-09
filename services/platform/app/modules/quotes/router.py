from uuid import UUID

from fastapi import APIRouter, Request

from app.deps import KeyDep, SessionDep, StaffDep, UserDep, client_ip
from app.http import command, dump
from app.modules.quotes import service
from app.modules.quotes.schemas import (
    AdjustmentBody,
    CancellationBody,
    ChangeRequestBody,
    DecisionBody,
    DocumentBody,
    DocumentPatch,
    ItineraryBody,
    ModuleEdit,
    QuotePatch,
    ServiceLineEventBody,
    SignoffBody,
)

router = APIRouter(tags=["quotes"])


@router.post("/v1/cases/{case_id}/quotes", status_code=201)
async def create_quote(case_id: UUID, actor: StaffDep, session: SessionDep):
    return dump(await service.create_quote(session, actor, case_id))


@router.get("/v1/cases/{case_id}/quotes")
async def list_quotes(case_id: UUID, actor: UserDep, session: SessionDep, visibility: str | None = None):
    return dump(await service.list_quotes(session, actor, case_id, visibility))


@router.patch("/v1/quotes/{quote_id}")
async def patch_quote(quote_id: UUID, body: QuotePatch, actor: StaffDep, session: SessionDep):
    return dump(await service.patch_quote(session, actor, quote_id, body))


@router.patch("/v1/quotes/{quote_id}/modules/{module_id}")
async def patch_module(quote_id: UUID, module_id: UUID, body: ModuleEdit, actor: StaffDep, session: SessionDep):
    return dump(await service.patch_module(session, actor, quote_id, module_id, body))


@router.post("/v1/quotes/{quote_id}/adjustments", status_code=201)
async def adjustment(quote_id: UUID, body: AdjustmentBody, actor: StaffDep, session: SessionDep):
    return dump(await service.add_adjustment(session, actor, quote_id, body))


@router.post("/v1/quotes/{quote_id}/publish")
async def publish(quote_id: UUID, actor: StaffDep, session: SessionDep, key: KeyDep):
    return await command(session, actor, key, {"quoteId": str(quote_id)}, 200, lambda: service.publish_quote(session, actor, quote_id))


@router.post("/v1/quotes/{quote_id}/modules/{module_id}/decision")
async def decision(quote_id: UUID, module_id: UUID, body: DecisionBody, actor: UserDep, session: SessionDep, key: KeyDep):
    return await command(
        session,
        actor,
        key,
        {"quoteId": str(quote_id), "moduleId": str(module_id), **body.model_dump(mode="json")},
        200,
        lambda: service.decide(session, actor, quote_id, module_id, body),
    )


@router.post("/v1/quotes/{quote_id}/change-requests", status_code=201)
async def change(quote_id: UUID, body: ChangeRequestBody, actor: UserDep, session: SessionDep, key: KeyDep):
    return await command(
        session,
        actor,
        key,
        {"quoteId": str(quote_id), **body.model_dump(mode="json")},
        201,
        lambda: service.change_request(session, actor, quote_id, body),
    )


@router.post("/v1/quotes/{quote_id}/signoff")
async def signoff(quote_id: UUID, body: SignoffBody, actor: UserDep, session: SessionDep, request: Request, key: KeyDep):
    return await command(
        session,
        actor,
        key,
        {"quoteId": str(quote_id), **body.model_dump(mode="json")},
        200,
        lambda: service.signoff(
            session,
            actor,
            quote_id,
            body,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        ),
    )


@router.post("/v1/quotes/{quote_id}/decline")
async def decline(quote_id: UUID, actor: UserDep, session: SessionDep, key: KeyDep):
    return await command(session, actor, key, {"quoteId": str(quote_id)}, 200, lambda: service.decline_quote(session, actor, quote_id))


@router.get("/v1/bookings/{booking_id}/commercial-summary")
async def summary(booking_id: UUID, actor: UserDep, session: SessionDep):
    return await service.commercial_summary(session, actor, booking_id)


@router.get("/v1/cases/{case_id}/itinerary")
async def itinerary(case_id: UUID, actor: UserDep, session: SessionDep):
    return await service.list_itinerary(session, actor, case_id)


@router.post("/v1/cases/{case_id}/itinerary-items", status_code=201)
async def add_item(case_id: UUID, body: ItineraryBody, actor: StaffDep, session: SessionDep):
    return await service.add_itinerary(session, actor, case_id, body)


@router.post("/v1/service-lines/{line_id}/events", status_code=201)
async def line_event(line_id: UUID, body: ServiceLineEventBody, actor: StaffDep, session: SessionDep):
    return await service.add_service_event(session, actor, line_id, body)


@router.get("/v1/cases/{case_id}/document-requirements")
async def documents(case_id: UUID, actor: UserDep, session: SessionDep):
    return await service.list_documents(session, actor, case_id)


@router.post("/v1/cases/{case_id}/document-requirements", status_code=201)
async def add_document(case_id: UUID, body: DocumentBody, actor: StaffDep, session: SessionDep):
    return await service.add_document(session, actor, case_id, body)


@router.patch("/v1/cases/{case_id}/document-requirements/{requirement_id}")
async def patch_document(
    case_id: UUID,
    requirement_id: UUID,
    body: DocumentPatch,
    actor: UserDep,
    session: SessionDep,
):
    return await service.patch_document(session, actor, case_id, requirement_id, body)


@router.post("/v1/bookings/{booking_id}/cancellation-requests", status_code=201)
async def cancel(booking_id: UUID, body: CancellationBody, actor: UserDep, session: SessionDep):
    return await service.request_cancellation(session, actor, booking_id, body)


@router.post("/v1/cancellation-requests/{request_id}/decide")
async def decide_cancel(request_id: UUID, actor: StaffDep, session: SessionDep, approved: bool = True):
    return await service.decide_cancellation(session, actor, request_id, approved)

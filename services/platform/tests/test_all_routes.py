import os
from uuid import uuid4

import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.modules.cases.router import router as cases_router
from app.modules.catalogue.router import router as catalogue_router
from app.modules.clinical.router import router as clinical_router
from app.modules.engagement.router import router as engagement_router
from app.modules.identity.router import router as identity_router
from app.modules.quotes.router import router as quotes_router
from app.security import totp_code

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://integration_user:integration@localhost:5432/trawellcare_test",
)
PHONE = "+96895550001"
SLOTS = {
    "patient_name": "Amina Said",
    "home_country": "OM",
    "home_city": "Muscat",
    "procedure_interest": "IVF",
    "destination_interest": "India",
    "travel_window": "2026-11",
    "budget_band": "medium",
    "companion_count": 1,
    "language": "en",
}


def _routes() -> set[tuple[str, str]]:
    found = {("GET", "/health"), ("GET", "/ready")}
    routers = (identity_router, cases_router, catalogue_router, clinical_router, quotes_router, engagement_router)
    for router in routers:
        for route in router.routes:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None) or set()
            if not path:
                continue
            for method in methods - {"HEAD", "OPTIONS"}:
                found.add((method, path))
    return found


async def _age() -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as connection:
        await connection.execute(text("UPDATE platform.otp_challenges SET created_at = now() - interval '2 minutes'"))
    await engine.dispose()


async def _line_id(booking_id: str) -> str:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.connect() as connection:
        value = await connection.scalar(
            text("SELECT id FROM platform.service_lines WHERE booking_id = :id"),
            {"id": booking_id},
        )
    await engine.dispose()
    return str(value)


def _sub(token: str) -> str:
    return jwt.decode(token, options={"verify_signature": False}, algorithms=["RS256"])["sub"]


async def test_every_route(api, monkeypatch):
    monkeypatch.setattr("app.modules.identity.service.generate_otp_code", lambda: "123456")
    client = api
    called: set[tuple[str, str]] = set()

    async def call(method: str, path: str, *, route: str, status: int = 200, **kwargs):
        response = await getattr(client, method)(path, **kwargs)
        assert response.status_code == status, f"{method.upper()} {path} -> {response.status_code} {response.text}"
        called.add((method.upper(), route))
        if "application/json" in response.headers.get("content-type", ""):
            return response.json()
        return None

    started = await call(
        "post",
        "/v1/auth/phone/start",
        route="/v1/auth/phone/start",
        json={"phoneE164": PHONE, "locale": "en", "purpose": "login"},
    )
    await _age()
    resent = await call(
        "post",
        "/v1/auth/phone/resend",
        route="/v1/auth/phone/resend",
        json={"challengeId": started["challengeId"]},
    )
    verified = await call(
        "post",
        "/v1/auth/phone/verify",
        route="/v1/auth/phone/verify",
        json={"challengeId": resent["challengeId"], "code": "123456"},
    )
    customer = {"Authorization": f"Bearer {verified['accessToken']}"}
    customer_id = verified["customerId"]
    refreshed = await call(
        "post",
        "/v1/auth/refresh",
        route="/v1/auth/refresh",
        json={"refreshToken": verified["refreshToken"]},
    )
    customer = {"Authorization": f"Bearer {refreshed['accessToken']}"}

    me = await call("get", "/v1/customers/me", route="/v1/customers/me", headers=customer)
    assert me["id"] == customer_id
    await call(
        "patch",
        "/v1/customers/me",
        route="/v1/customers/me",
        headers=customer,
        json={"displayName": "Amina Said", "timezone": "Asia/Muscat"},
    )
    companion = await call(
        "post",
        "/v1/customers/me/companions",
        route="/v1/customers/me/companions",
        status=201,
        headers=customer,
        json={"displayName": "Sara Said", "relationship": "sister"},
    )
    await call("get", "/v1/customers/me/companions", route="/v1/customers/me/companions", headers=customer)
    await call(
        "patch",
        f"/v1/customers/me/companions/{companion['id']}",
        route="/v1/customers/me/companions/{companion_id}",
        headers=customer,
        json={"nationality": "OM"},
    )
    consent = await call(
        "post",
        "/v1/customers/me/consents",
        route="/v1/customers/me/consents",
        status=201,
        headers=customer,
        json={"purpose": "marketing", "textVersion": "1"},
    )
    await call(
        "post",
        f"/v1/customers/me/consents/{consent['id']}/withdraw",
        route="/v1/customers/me/consents/{consent_id}/withdraw",
        headers=customer,
    )
    registered = await call(
        "post",
        "/v1/auth/customer/register",
        route="/v1/auth/customer/register",
        headers=customer,
        json={"email": "amina@example.com", "password": "secret-pass-1"},
    )
    await call(
        "post",
        "/v1/auth/customer/verify-email",
        route="/v1/auth/customer/verify-email",
        headers=customer,
        json={"challengeId": registered["challengeId"], "code": "123456"},
    )
    await call(
        "post",
        "/v1/auth/customer/login",
        route="/v1/auth/customer/login",
        json={"email": "amina@example.com", "password": "secret-pass-1"},
    )

    ops_token = await _staff(call, "ops@trawellcare.local")
    doctor_token = await _staff(call, "doctor@trawellcare.local")
    ops = {"Authorization": f"Bearer {ops_token}"}
    doctor = {"Authorization": f"Bearer {doctor_token}"}

    handoff = await call(
        "post",
        "/v1/enquiries",
        route="/v1/enquiries",
        status=201,
        headers={"X-Api-Key": "test-platform-key", "Idempotency-Key": "all-handoff"},
        json={"conversationId": str(uuid4()), "customerId": customer_id, "extractedSlots": SLOTS, "turns": []},
    )
    case_id = handoff["caseId"]
    enquiry_id = handoff["enquiryId"]
    await call("get", f"/v1/enquiries/{enquiry_id}", route="/v1/enquiries/{enquiry_id}", headers=ops)
    await call("get", f"/v1/enquiries/{enquiry_id}/turns", route="/v1/enquiries/{enquiry_id}/turns", headers=ops)
    await call(
        "post",
        f"/v1/enquiries/{enquiry_id}/contact-attempts",
        route="/v1/enquiries/{enquiry_id}/contact-attempts",
        status=201,
        headers=ops,
        json={"channel": "call", "outcome": "reached", "notes": "Spoke with Amina"},
    )
    tasks = await call("get", f"/v1/cases/{case_id}/tasks", route="/v1/cases/{case_id}/tasks", headers=ops)
    await call("post", f"/v1/tasks/{tasks[0]['id']}/complete", route="/v1/tasks/{task_id}/complete", headers=ops)
    await call(
        "post",
        f"/v1/enquiries/{enquiry_id}/qualification",
        route="/v1/enquiries/{enquiry_id}/qualification",
        headers={**ops, "Idempotency-Key": "all-qual"},
        json={"outcome": "qualified", "dispositionCode": "PROCEED_MEDICAL"},
    )
    await call(
        "patch",
        f"/v1/cases/{case_id}",
        route="/v1/cases/{case_id}",
        headers=ops,
        json={"priority": "urgent"},
    )
    case = await call("get", f"/v1/cases/{case_id}", route="/v1/cases/{case_id}", headers=customer)
    patient = next(party for party in case["parties"] if party["role"] == "patient")
    await call(
        "post",
        f"/v1/cases/{case_id}/parties",
        route="/v1/cases/{case_id}/parties",
        status=201,
        headers=ops,
        json={"role": "emergency_contact", "displayName": "Omar Said", "phoneE164": "+96891112233"},
    )
    await call(
        "post",
        f"/v1/cases/{case_id}/stage",
        route="/v1/cases/{case_id}/stage",
        headers=ops,
        json={"toStage": "planning"},
    )
    await call(
        "post",
        f"/v1/cases/{case_id}/notes",
        route="/v1/cases/{case_id}/notes",
        status=201,
        headers=ops,
        json={"audience": "patient", "body": "We will call you tomorrow."},
    )
    assignment = await call(
        "post",
        f"/v1/cases/{case_id}/assignments",
        route="/v1/cases/{case_id}/assignments",
        status=201,
        headers=ops,
        json={"assigneeId": _sub(ops_token), "role": "wellness_curator"},
    )
    await call(
        "post",
        f"/v1/cases/{case_id}/assignments/{assignment['id']}/end",
        route="/v1/cases/{case_id}/assignments/{assignment_id}/end",
        headers=ops,
    )
    await call("get", "/v1/customers/me/cases", route="/v1/customers/me/cases", headers=customer)
    await call("get", f"/v1/cases/{case_id}/journey", route="/v1/cases/{case_id}/journey", headers=customer)
    await call("get", "/v1/staff/queue", route="/v1/staff/queue", headers=ops)
    await call("get", "/v1/staff/sla-breaches", route="/v1/staff/sla-breaches", headers=ops)
    await call("get", "/v1/staff/dispositions", route="/v1/staff/dispositions", headers=ops)

    hospital = await call(
        "post",
        "/v1/staff/hospitals",
        route="/v1/staff/hospitals",
        status=201,
        headers=ops,
        json={"nameEn": "City Hospital", "country": "IN", "city": "Mumbai", "rating": "4.2"},
    )
    await call("get", "/v1/staff/hospitals", route="/v1/staff/hospitals", headers=ops)
    await call(
        "patch",
        f"/v1/staff/hospitals/{hospital['id']}",
        route="/v1/staff/hospitals/{hospital_id}",
        headers=ops,
        json={"active": False},
    )
    await call(
        "post",
        "/v1/staff/doctors",
        route="/v1/staff/doctors",
        status=201,
        headers=ops,
        json={"nameEn": "Dr Extra", "specialty": "cardiology", "hospitalId": hospital["id"]},
    )
    doctors = await call("get", "/v1/staff/doctors", route="/v1/staff/doctors", headers=ops)
    sample = next(row for row in doctors if row["nameEn"] == "Dr Sample")
    procedure = await call(
        "post",
        "/v1/staff/procedures",
        route="/v1/staff/procedures",
        status=201,
        headers=ops,
        json={"slug": "cardiac", "specialty": "cardiology", "nameEn": "Cardiac review", "hospitalId": hospital["id"]},
    )
    await call("get", "/v1/staff/procedures", route="/v1/staff/procedures", headers=ops)
    await call(
        "post",
        "/v1/staff/packages",
        route="/v1/staff/packages",
        status=201,
        headers=ops,
        json={"nameEn": "City package", "hospitalId": hospital["id"], "components": [{"moduleType": "hospital", "description": "Consult"}]},
    )
    await call("get", "/v1/staff/packages", route="/v1/staff/packages", headers=ops)
    tariff = await call(
        "post",
        "/v1/staff/tariffs",
        route="/v1/staff/tariffs",
        status=201,
        headers=ops,
        json={"hospitalId": hospital["id"], "procedureId": procedure["id"], "currency": "INR", "amountMinor": 900000},
    )
    await call("get", "/v1/staff/tariffs", route="/v1/staff/tariffs", headers=ops)
    await call(
        "put",
        f"/v1/staff/tariffs/{tariff['id']}",
        route="/v1/staff/tariffs/{tariff_id}",
        headers=ops,
        json={"currency": "INR", "amountMinor": 950000},
    )

    await call(
        "put",
        f"/v1/cases/{case_id}/clinical-profile",
        route="/v1/cases/{case_id}/clinical-profile",
        headers=ops,
        json={"allergies": "None recorded", "medications": "None"},
    )
    await call("get", f"/v1/cases/{case_id}/clinical-profile", route="/v1/cases/{case_id}/clinical-profile", headers=ops)
    await call(
        "put",
        f"/v1/cases/{case_id}/parties/{patient['id']}/travel-profile",
        route="/v1/cases/{case_id}/parties/{party_id}/travel-profile",
        headers=ops,
        json={"nationality": "OM", "passportCountry": "OM", "passportExpiry": "2030-01-01"},
    )
    booked = await call(
        "post",
        f"/v1/cases/{case_id}/consultations",
        route="/v1/cases/{case_id}/consultations",
        status=201,
        headers=ops,
        json={"doctorId": sample["id"], "scheduledAt": "2026-12-01T10:00:00Z", "meetingLink": "https://meet.example/a"},
    )
    moved = await call(
        "post",
        f"/v1/consultations/{booked['id']}/reschedule",
        route="/v1/consultations/{consultation_id}/reschedule",
        status=201,
        headers=ops,
        json={"scheduledAt": "2026-12-02T10:00:00Z", "reason": "Patient asked for the next day"},
    )
    await call("get", f"/v1/cases/{case_id}/consultations", route="/v1/cases/{case_id}/consultations", headers=customer)
    await call(
        "post",
        f"/v1/consultations/{moved['id']}/outcome",
        route="/v1/consultations/{consultation_id}/outcome",
        headers=doctor,
        json={"outcome": "Fit to travel", "issueIdentified": "None", "clinicalNote": "Staff only"},
    )
    plans = await call("post", f"/v1/cases/{case_id}/care-plans", route="/v1/cases/{case_id}/care-plans", status=201, headers=ops)
    await call(
        "patch",
        f"/v1/care-plans/{plans[0]['id']}/modules/{plans[0]['modules'][0]['id']}",
        route="/v1/care-plans/{plan_id}/modules/{module_id}",
        headers=ops,
        json={"title": "IVF package", "amountMinor": 1700000, "priceOverrideReason": "Negotiated rate"},
    )
    await call("get", f"/v1/cases/{case_id}/care-plans", route="/v1/cases/{case_id}/care-plans", headers=ops)
    await call("get", f"/v1/staff/cases/{case_id}/match-preview", route="/v1/staff/cases/{case_id}/match-preview", headers=ops)
    selected = await call(
        "post",
        f"/v1/care-plans/{plans[0]['id']}/select",
        route="/v1/care-plans/{plan_id}/select",
        headers=ops,
        json={"selectionReason": "Negotiated rate"},
    )
    quote_id = selected["quoteId"]
    await call("post", f"/v1/cases/{case_id}/quotes", route="/v1/cases/{case_id}/quotes", status=201, headers=ops)
    await call(
        "patch",
        f"/v1/quotes/{quote_id}",
        route="/v1/quotes/{quote_id}",
        headers=ops,
        json={"validUntil": "2026-12-31T00:00:00Z"},
    )
    quote = await call("get", f"/v1/cases/{case_id}/quotes", route="/v1/cases/{case_id}/quotes", headers=ops)
    module_id = quote[0]["modules"][0]["id"]
    await call(
        "patch",
        f"/v1/quotes/{quote_id}/modules/{module_id}",
        route="/v1/quotes/{quote_id}/modules/{module_id}",
        headers=ops,
        json={"supplierName": "Sample Hospital"},
    )
    await call(
        "post",
        f"/v1/quotes/{quote_id}/adjustments",
        route="/v1/quotes/{quote_id}/adjustments",
        status=201,
        headers=ops,
        json={"kind": "discount", "amountMinor": 1000, "currency": quote[0]["currency"], "reason": "Courtesy"},
    )
    await call(
        "post",
        f"/v1/quotes/{quote_id}/publish",
        route="/v1/quotes/{quote_id}/publish",
        headers={**ops, "Idempotency-Key": "all-publish"},
    )
    published = await call(
        "get",
        f"/v1/cases/{case_id}/quotes?visibility=customer",
        route="/v1/cases/{case_id}/quotes",
        headers=customer,
    )
    rejected_module = published[0]["modules"][0]["id"]
    await call(
        "post",
        f"/v1/quotes/{quote_id}/modules/{rejected_module}/decision",
        route="/v1/quotes/{quote_id}/modules/{module_id}/decision",
        headers={**customer, "Idempotency-Key": "all-reject"},
        json={"decision": "reject", "rejectReason": "Dates do not work"},
    )
    await call(
        "post",
        f"/v1/quotes/{quote_id}/change-requests",
        route="/v1/quotes/{quote_id}/change-requests",
        status=201,
        headers={**customer, "Idempotency-Key": "all-change"},
        json={"moduleId": rejected_module, "reason": "Find another hospital"},
    )
    await call(
        "post",
        f"/v1/quotes/{quote_id}/publish",
        route="/v1/quotes/{quote_id}/publish",
        headers={**ops, "Idempotency-Key": "all-republish"},
    )
    revised = await call(
        "get",
        f"/v1/cases/{case_id}/quotes?visibility=customer",
        route="/v1/cases/{case_id}/quotes",
        headers=customer,
    )
    for index, module in enumerate(revised[0]["modules"]):
        await call(
            "post",
            f"/v1/quotes/{quote_id}/modules/{module['id']}/decision",
            route="/v1/quotes/{quote_id}/modules/{module_id}/decision",
            headers={**customer, "Idempotency-Key": f"all-accept-{index}"},
            json={"decision": "accept"},
        )
    await _age()
    sign_start = await call(
        "post",
        "/v1/auth/phone/start",
        route="/v1/auth/phone/start",
        headers=customer,
        json={"phoneE164": PHONE, "purpose": "signoff"},
    )
    sign_check = await call(
        "post",
        "/v1/auth/phone/verify",
        route="/v1/auth/phone/verify",
        json={"challengeId": sign_start["challengeId"], "code": "123456"},
    )
    assert sign_check["verified"] is True
    signed = await call(
        "post",
        f"/v1/quotes/{quote_id}/signoff",
        route="/v1/quotes/{quote_id}/signoff",
        headers={**customer, "Idempotency-Key": "all-sign"},
        json={"version": revised[0]["version"], "otpChallengeId": sign_start["challengeId"], "consentAccepted": True},
    )
    await call(
        "get",
        f"/v1/bookings/{signed['bookingId']}/commercial-summary",
        route="/v1/bookings/{booking_id}/commercial-summary",
        headers=customer,
    )
    await call("get", f"/v1/cases/{case_id}/itinerary", route="/v1/cases/{case_id}/itinerary", headers=customer)
    await call(
        "post",
        f"/v1/cases/{case_id}/itinerary-items",
        route="/v1/cases/{case_id}/itinerary-items",
        status=201,
        headers=ops,
        json={"kind": "flight", "title": "Muscat to Chennai", "location": "MCT"},
    )
    line_id = await _line_id(signed["bookingId"])
    await call(
        "post",
        f"/v1/service-lines/{line_id}/events",
        route="/v1/service-lines/{line_id}/events",
        status=201,
        headers=ops,
        json={"status": "confirmed", "manualConfirmation": True, "note": "Manual hold"},
    )
    requirement = await call(
        "post",
        f"/v1/cases/{case_id}/document-requirements",
        route="/v1/cases/{case_id}/document-requirements",
        status=201,
        headers=ops,
        json={"code": "passport", "casePartyId": patient["id"]},
    )
    await call("get", f"/v1/cases/{case_id}/document-requirements", route="/v1/cases/{case_id}/document-requirements", headers=customer)
    await call(
        "patch",
        f"/v1/cases/{case_id}/document-requirements/{requirement['id']}",
        route="/v1/cases/{case_id}/document-requirements/{requirement_id}",
        headers=customer,
        json={"status": "uploaded"},
    )
    cancellation = await call(
        "post",
        f"/v1/bookings/{signed['bookingId']}/cancellation-requests",
        route="/v1/bookings/{booking_id}/cancellation-requests",
        status=201,
        headers=customer,
        json={"reason": "Dates changed"},
    )
    await call(
        "post",
        f"/v1/cancellation-requests/{cancellation['id']}/decide?approved=false",
        route="/v1/cancellation-requests/{request_id}/decide",
        headers=ops,
    )
    review = await call(
        "post",
        f"/v1/cases/{case_id}/reviews",
        route="/v1/cases/{case_id}/reviews",
        status=201,
        headers=customer,
        json={"rating": 5, "body": "Clear and careful"},
    )
    await call(
        "post",
        f"/v1/reviews/{review['id']}/moderate",
        route="/v1/reviews/{review_id}/moderate",
        headers=ops,
        json={"status": "published"},
    )
    await call("post", "/v1/customers/me/referrals", route="/v1/customers/me/referrals", status=201, headers=customer)
    await call("get", "/v1/customers/me/points", route="/v1/customers/me/points", headers=customer)
    follow = await call(
        "post",
        f"/v1/cases/{case_id}/follow-ups",
        route="/v1/cases/{case_id}/follow-ups",
        status=201,
        headers=ops,
    )
    await call(
        "post",
        f"/v1/follow-ups/{follow['id']}/complete",
        route="/v1/follow-ups/{follow_id}/complete",
        headers=ops,
        json={"outcome": "reached", "notes": "Patient is well"},
    )
    await call("get", "/v1/reports/funnel", route="/v1/reports/funnel", headers=ops)
    await call("get", "/v1/reports/sla", route="/v1/reports/sla", headers=ops)
    await call("get", "/v1/reports/qualification", route="/v1/reports/qualification", headers=ops)
    await call(
        "post",
        "/v1/internal/events",
        route="/v1/internal/events",
        headers={"X-Api-Key": "test-platform-key"},
        json={"eventId": str(uuid4()), "type": "payment.succeeded.v1", "payload": {"bookingId": signed["bookingId"]}},
    )

    second = await call(
        "post",
        "/v1/enquiries",
        route="/v1/enquiries",
        status=201,
        headers={"X-Api-Key": "test-platform-key", "Idempotency-Key": "all-handoff-2"},
        json={"conversationId": str(uuid4()), "customerId": customer_id, "extractedSlots": SLOTS, "turns": []},
    )
    await call(
        "post",
        f"/v1/enquiries/{second['enquiryId']}/qualification",
        route="/v1/enquiries/{enquiry_id}/qualification",
        headers={**ops, "Idempotency-Key": "all-qual-2"},
        json={"outcome": "qualified", "dispositionCode": "PROCEED_MEDICAL"},
    )
    second_plans = await call(
        "post",
        f"/v1/cases/{second['caseId']}/care-plans",
        route="/v1/cases/{case_id}/care-plans",
        status=201,
        headers=ops,
    )
    second_quote = await call(
        "post",
        f"/v1/care-plans/{second_plans[0]['id']}/select",
        route="/v1/care-plans/{plan_id}/select",
        headers=ops,
        json={"selectionReason": "Decline path"},
    )
    await call(
        "post",
        f"/v1/quotes/{second_quote['quoteId']}/publish",
        route="/v1/quotes/{quote_id}/publish",
        headers={**ops, "Idempotency-Key": "all-publish-b"},
    )
    await call(
        "post",
        f"/v1/quotes/{second_quote['quoteId']}/decline",
        route="/v1/quotes/{quote_id}/decline",
        headers={**customer, "Idempotency-Key": "all-decline"},
    )
    await call(
        "post",
        f"/v1/cases/{second['caseId']}/close",
        route="/v1/cases/{case_id}/close",
        headers={**ops, "Idempotency-Key": "all-close"},
        json={"dispositionCode": "UNREACHABLE", "reason": "Patient declined"},
    )

    await call("get", "/health", route="/health")
    await call("get", "/ready", route="/ready")
    await call("post", "/v1/auth/logout", route="/v1/auth/logout", headers=customer, json={})
    stale = await client.post("/v1/auth/refresh", json={"refreshToken": refreshed["refreshToken"]})
    assert stale.status_code == 401

    expected = _routes()
    missing = sorted(expected - called)
    extra = sorted(called - expected)
    assert not missing and not extra, f"missing={missing} extra={extra}"
    assert not any(method == "DELETE" for method, _path in expected)


async def _staff(call, email: str) -> str:
    started = await call(
        "post",
        "/v1/auth/staff/login",
        route="/v1/auth/staff/login",
        json={"email": email, "password": "staff-secret"},
    )
    confirmed = await call(
        "post",
        "/v1/auth/staff/totp",
        route="/v1/auth/staff/totp",
        json={"mfaToken": started["mfaToken"], "code": totp_code("JBSWY3DPEHPK3PXP")},
    )
    return confirmed["accessToken"]

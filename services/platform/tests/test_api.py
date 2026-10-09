import os
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.security import totp_code

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://integration_user:integration@localhost:5432/trawellcare_test",
)

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


async def _age_challenges() -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as connection:
        await connection.execute(text("UPDATE platform.otp_challenges SET created_at = now() - interval '2 minutes'"))
    await engine.dispose()


async def _customer(client, phone: str) -> tuple[str, str]:
    started = await client.post("/v1/auth/phone/start", json={"phoneE164": phone, "locale": "en", "purpose": "login"})
    assert started.status_code == 200, started.text
    verified = await client.post(
        "/v1/auth/phone/verify",
        json={"challengeId": started.json()["challengeId"], "code": "123456"},
    )
    assert verified.status_code == 200, verified.text
    body = verified.json()
    return body["accessToken"], body["customerId"]


async def _staff(client, email: str) -> str:
    started = await client.post("/v1/auth/staff/login", json={"email": email, "password": "staff-secret"})
    assert started.status_code == 200, started.text
    confirmed = await client.post(
        "/v1/auth/staff/totp",
        json={"mfaToken": started.json()["mfaToken"], "code": totp_code("JBSWY3DPEHPK3PXP")},
    )
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()["accessToken"]


async def test_health(api):
    response = await api.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_handoff_quote_signoff_and_access(api, monkeypatch):
    monkeypatch.setattr("app.modules.identity.service.generate_otp_code", lambda: "123456")
    token, customer_id = await _customer(api, "+96891234567")
    await _age_challenges()
    again, same_customer = await _customer(api, "+96891234567")
    assert same_customer == customer_id
    customer = {"Authorization": f"Bearer {token}"}

    handoff_body = {
        "conversationId": str(uuid4()),
        "customerId": customer_id,
        "extractedSlots": SLOTS,
        "turns": [{"ordinal": 1, "role": "user", "content": "I want to talk to a doctor"}],
    }
    created = await api.post(
        "/v1/enquiries",
        headers={"X-Api-Key": "test-platform-key", "Idempotency-Key": "handoff-1"},
        json=handoff_body,
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["caseId"]
    replay = await api.post(
        "/v1/enquiries",
        headers={"X-Api-Key": "test-platform-key", "Idempotency-Key": "handoff-1"},
        json=handoff_body,
    )
    assert replay.status_code == 201
    assert replay.json()["caseId"] == case_id
    conflict = await api.post(
        "/v1/enquiries",
        headers={"X-Api-Key": "test-platform-key", "Idempotency-Key": "handoff-1"},
        json={**handoff_body, "campaign": "changed"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"

    incomplete = await api.post(
        "/v1/enquiries",
        headers={"X-Api-Key": "test-platform-key", "Idempotency-Key": "handoff-bad"},
        json={"conversationId": str(uuid4()), "customerId": customer_id, "extractedSlots": {"patient_name": "Amina"}},
    )
    assert incomplete.status_code == 422
    assert incomplete.json()["code"] == "SLOTS_INCOMPLETE"

    me = await api.get("/v1/customers/me/cases", headers=customer)
    assert me.status_code == 200
    assert me.json()["items"][0]["ref"].startswith("CASE-")

    other_token, _ = await _customer(api, "+96890000001")
    hidden = await api.get(f"/v1/cases/{case_id}", headers={"Authorization": f"Bearer {other_token}"})
    assert hidden.status_code == 404

    ops = {"Authorization": f"Bearer {await _staff(api, 'ops@trawellcare.local')}"}
    auditor = {"Authorization": f"Bearer {await _staff(api, 'auditor@trawellcare.local')}"}
    enquiry_id = created.json()["enquiryId"]
    denied = await api.post(
        f"/v1/enquiries/{enquiry_id}/qualification",
        headers={**auditor, "Idempotency-Key": "qual-deny"},
        json={"outcome": "qualified", "dispositionCode": "PROCEED_MEDICAL"},
    )
    assert denied.status_code == 403

    qualified = await api.post(
        f"/v1/enquiries/{enquiry_id}/qualification",
        headers={**ops, "Idempotency-Key": "qual-1"},
        json={"outcome": "qualified", "dispositionCode": "PROCEED_MEDICAL"},
    )
    assert qualified.status_code == 200

    plans = await api.post(f"/v1/cases/{case_id}/care-plans", headers=ops)
    assert plans.status_code == 201, plans.text
    assert len(plans.json()) == 3
    selected = await api.post(
        f"/v1/care-plans/{plans.json()[0]['id']}/select",
        headers=ops,
        json={"selectionReason": "Closest clinical match"},
    )
    assert selected.status_code == 200, selected.text
    quote_id = selected.json()["quoteId"]
    published = await api.post(
        f"/v1/quotes/{quote_id}/publish",
        headers={**ops, "Idempotency-Key": "publish-1"},
    )
    assert published.status_code == 200, published.text

    listing = await api.get(f"/v1/cases/{case_id}/quotes", headers=customer)
    assert listing.status_code == 200
    module_id = listing.json()[0]["modules"][0]["id"]
    rejected = await api.post(
        f"/v1/quotes/{quote_id}/modules/{module_id}/decision",
        headers={**customer, "Idempotency-Key": "decision-reject"},
        json={"decision": "reject", "rejectReason": "Dates do not work"},
    )
    assert rejected.status_code == 200
    blocked = await api.post(
        "/v1/auth/phone/start",
        headers=customer,
        json={"phoneE164": "+96891234567", "purpose": "signoff"},
    )
    assert blocked.status_code == 200, blocked.text
    checked = await api.post(
        "/v1/auth/phone/verify",
        json={"challengeId": blocked.json()["challengeId"], "code": "123456"},
    )
    assert checked.json()["verified"] is True
    refused = await api.post(
        f"/v1/quotes/{quote_id}/signoff",
        headers={**customer, "Idempotency-Key": "sign-1"},
        json={"version": 1, "otpChallengeId": blocked.json()["challengeId"], "consentAccepted": True},
    )
    assert refused.status_code == 422
    assert refused.json()["code"] == "QUOTE_HAS_REJECTION"

    revised = await api.post(
        f"/v1/quotes/{quote_id}/change-requests",
        headers={**customer, "Idempotency-Key": "change-1"},
        json={"moduleId": module_id, "reason": "Find another hospital"},
    )
    assert revised.status_code == 201, revised.text
    republished = await api.post(
        f"/v1/quotes/{quote_id}/publish",
        headers={**ops, "Idempotency-Key": "publish-2"},
    )
    assert republished.status_code == 200, republished.text
    current = await api.get(f"/v1/cases/{case_id}/quotes?visibility=customer", headers=customer)
    pending = current.json()[0]
    assert pending["version"] == 2
    customer_again = {"Authorization": f"Bearer {again}"}
    accepted = await api.post(
        f"/v1/quotes/{quote_id}/modules/{pending['modules'][0]['id']}/decision",
        headers={**customer_again, "Idempotency-Key": "decision-accept"},
        json={"decision": "accept"},
    )
    assert accepted.status_code == 200, accepted.text
    await _age_challenges()
    sign_start = await api.post(
        "/v1/auth/phone/start",
        headers=customer_again,
        json={"phoneE164": "+96891234567", "purpose": "signoff"},
    )
    assert sign_start.status_code == 200, sign_start.text
    sign_check = await api.post(
        "/v1/auth/phone/verify",
        json={"challengeId": sign_start.json()["challengeId"], "code": "123456"},
    )
    signed = await api.post(
        f"/v1/quotes/{quote_id}/signoff",
        headers={**customer_again, "Idempotency-Key": "sign-2"},
        json={
            "version": 2,
            "otpChallengeId": sign_start.json()["challengeId"],
            "consentAccepted": True,
        },
    )
    assert sign_check.status_code == 200
    assert signed.status_code == 200, signed.text
    assert signed.json()["bookingRef"].startswith("BK-")

    summary = await api.get(
        f"/v1/bookings/{signed.json()['bookingId']}/commercial-summary",
        headers=customer_again,
    )
    assert summary.status_code == 200
    assert summary.json()["paymentState"] == "unknown"
    assert "clinical" not in summary.text.lower()

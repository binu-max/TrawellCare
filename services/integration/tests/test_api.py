import json
import os
import uuid

import httpx

from app.jobs import process_once
from app.modules.vendors.models import Vendor


def _journey():
    return {
        "TUI": "search-tui",
        "Completed": "True",
        "CurrencyCode": "INR",
        "Code": "200",
        "Msg": ["Success"],
        "Trips": [
            {
                "Journey": [
                    {
                        "Index": "6E|1",
                        "Stops": 0,
                        "FlightNo": " 123",
                        "VAC": "6E",
                        "DepartureTime": "2026-11-15T10:00:00",
                        "ArrivalTime": "2026-11-15T14:00:00",
                        "From": "MCT",
                        "To": "COK",
                        "NetFare": 15000.5,
                        "GrossFare": 16000,
                    }
                ]
            }
        ],
    }


def benzy_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    body = json.loads(request.content.decode() or "{}")
    benzy_handler.calls.append((path, body, request.headers.get("authorization")))
    if path.endswith("/Utils/Signature"):
        return httpx.Response(
            200,
            json={"Token": "tok-123", "ClientID": "enc-client", "Code": "200", "TUI": "sig-tui", "Msg": ["Success"]},
        )
    if path.endswith("/ExpressSearch"):
        assert body["Trips"][0]["From"] == "MCT"
        assert body["ChannelID"] == "b2bsaudideals"
        return httpx.Response(200, json={"TUI": "search-tui", "Code": "200", "Msg": ["Success"]})
    if path.endswith("/GetExpSearch"):
        return httpx.Response(200, json=_journey())
    if path.endswith("/SmartPricer"):
        return httpx.Response(200, json={"TUI": "price-tui", "Code": "200", "NetAmount": 14000, "Msg": ["Success"]})
    if path.endswith("/GetSPricer"):
        return httpx.Response(
            200,
            json={"TUI": "price-tui", "Code": "200", "NetAmount": 14000, "CurrencyCode": "INR", "Msg": ["Success"]},
        )
    if path.endswith("/CreateItinerary"):
        return httpx.Response(
            200,
            json={"TUI": "itin-tui", "TransactionID": 230003316, "NetAmount": 14000, "Code": "200", "Msg": ["Success"]},
        )
    if path.endswith("/StartPay"):
        return httpx.Response(200, json={"TUI": "itin-tui", "Code": "200", "TransactionID": 230003316, "Msg": ["Success"]})
    if path.endswith("/GetItineraryStatus"):
        return httpx.Response(
            200,
            json={"TUI": "itin-tui", "Code": "200", "CurrentStatus": "Success", "PaymentStatus": "Success", "Msg": ["Success"]},
        )
    if path.endswith("/Cancel"):
        assert body["TransactionID"] == 230003316
        assert body["Trips"][0]["Journey"][0]["Segments"][0]["CRSPNR"] == "TLGS8K"
        return httpx.Response(
            200,
            json={"TUI": "cancel-tui", "TransactionID": 230003316, "CancellationID": 1, "Code": "200", "Msg": ["Success"]},
        )
    if path.endswith("/RetrieveBooking"):
        return httpx.Response(
            200,
            json={
                "Code": "200",
                "TransactionID": 230003316,
                "Trips": [{"Journey": [{"Segments": [{"Flight": {"CRSPNR": "TLGS8K"}, "Pax": [{"ID": 9, "Ticket": ""}]}]}]}],
            },
        )
    return httpx.Response(500, json={"Msg": [f"unexpected {path}"]})


benzy_handler.calls = []


async def use_benzy(app):
    benzy_handler.calls = []
    await app.state.http.aclose()
    app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(benzy_handler))


async def test_health_is_open(api):
    client, _app = api
    response = await client.get("/health", headers={})
    # default client header is set; health must also work without it
    bare = httpx.ASGITransport(app=_app)
    async with httpx.AsyncClient(transport=bare, base_url="http://test") as plain:
        opened = await plain.get("/health")
    assert opened.status_code == 200
    assert response.status_code == 200


async def test_vendors_require_api_key(api):
    _client, app = api
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as plain:
        response = await plain.get("/v1/vendors")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


async def test_vendor_routing_rules(api):
    client, app = api
    listed = await client.get("/v1/vendors")
    assert listed.status_code == 200
    codes = {row["code"] for row in listed.json()["vendors"]}
    assert codes == {"akbar", "manual"}

    case_id = str(uuid.uuid4())
    created = await client.post(f"/v1/cases/{case_id}/travel-requests", json={"product": "flight"})
    assert created.status_code == 201
    assert created.json()["vendorCode"] == "akbar"

    missing = await client.post(
        f"/v1/cases/{case_id}/travel-requests",
        json={"vendorCode": "no-such-vendor", "product": "flight"},
    )
    assert missing.status_code == 404

    disabled = await client.patch("/v1/vendors/akbar", json={"enabled": False})
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    blocked = await client.post(
        f"/v1/cases/{case_id}/travel-requests",
        json={"vendorCode": "akbar", "product": "flight"},
    )
    assert blocked.status_code == 422
    assert blocked.json()["code"] == "VENDOR_DISABLED"

    await client.patch("/v1/vendors/akbar", json={"enabled": True})
    async with app.state.session_factory() as session:
        session.add(
            Vendor(
                code="gokite",
                display_name="Go Kite",
                adapter_type="benzy_flight",
                product="flight",
                enabled=True,
                config={},
                secret_prefix="VENDOR_GOKITE",
            )
        )
        await session.commit()
    ambiguous = await client.post(f"/v1/cases/{case_id}/travel-requests", json={"product": "flight"})
    assert ambiguous.status_code == 422
    assert ambiguous.json()["code"] == "VENDOR_REQUIRED"
    named = await client.post(
        f"/v1/cases/{case_id}/travel-requests",
        json={"vendorCode": "gokite", "product": "flight"},
    )
    assert named.status_code == 201
    assert named.json()["vendorCode"] == "gokite"


async def test_seed_does_not_turn_a_vendor_back_on(api):
    client, app = api
    from app.seed import seed

    await client.patch("/v1/vendors/akbar", json={"enabled": False})
    async with app.state.session_factory() as session:
        await seed(session)
        await session.commit()
    listed = await client.get("/v1/vendors")
    akbar = next(row for row in listed.json()["vendors"] if row["code"] == "akbar")
    assert akbar["enabled"] is False


async def test_akbar_search_price_and_confirm(api):
    client, app = api
    await use_benzy(app)
    case_id = str(uuid.uuid4())
    created = await client.post(
        f"/v1/cases/{case_id}/travel-requests",
        json={
            "vendorCode": "akbar",
            "search": {
                "origin": "MCT",
                "destination": "COK",
                "departDate": "2026-11-15",
                "adults": 1,
                "cabin": "economy",
            },
        },
    )
    request_id = created.json()["id"]
    searched = await client.post(f"/v1/travel-requests/{request_id}/search")
    assert searched.status_code == 200, searched.text
    option = searched.json()["options"][0]
    assert option["airlineCode"] == "6E"
    assert option["flightNumber"] == "123"
    assert option["amountMinor"] == 1500050
    assert option["cabin"] == "economy"

    signature = benzy_handler.calls[0][1]
    assert signature["MerchantID"] == os.environ["VENDOR_AKBAR_MERCHANT_ID"]
    assert signature["ApiKey"] == os.environ["VENDOR_AKBAR_API_KEY"]
    assert benzy_handler.calls[1][2] == "Bearer tok-123"

    priced = await client.post(f"/v1/travel-requests/{request_id}/price", json={"optionId": option["id"]})
    assert priced.status_code == 200
    assert priced.json()["status"] == "priced"
    assert priced.json()["amountMinor"] == 1400000

    confirmed = await client.post(
        f"/v1/travel-requests/{request_id}/confirm",
        headers={"Idempotency-Key": "confirm-1"},
        json={
            "optionId": option["id"],
            "contact": {
                "firstName": "Test",
                "lastName": "Patient",
                "email": "patient@example.com",
                "mobile": "+96891234567",
            },
            "passengers": [
                {
                    "title": "Mr",
                    "firstName": "TESTA",
                    "lastName": "TESTAB",
                    "dateOfBirth": "1987-08-27",
                    "gender": "M",
                    "nationality": "OM",
                    "passportNumber": "HM8888HJJ6K",
                }
            ],
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirming"

    await process_once(app.state.session_factory, app.state.settings, app.state.http)
    fetched = await client.get(f"/v1/travel-requests/{request_id}")
    assert fetched.json()["status"] == "confirmed"
    assert fetched.json()["supplierReference"] == "TLGS8K"
    cancelled = await client.post(f"/v1/travel-requests/{request_id}/cancel", json={"remarks": "test cancel"})
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    async with app.state.session_factory() as session:
        from sqlalchemy import select

        from app.modules.travel.models import TravelCall

        calls = list(await session.scalars(select(TravelCall)))
        dumped = json.dumps([call.request_body for call in calls])
    assert os.environ["VENDOR_AKBAR_PASSWORD"] not in dumped
    assert os.environ["VENDOR_AKBAR_API_KEY"] not in dumped


async def test_manual_confirm_is_idempotent(api):
    client, _app = api
    case_id = str(uuid.uuid4())
    created = await client.post(
        f"/v1/cases/{case_id}/travel-requests",
        json={"vendorCode": "manual", "product": "flight"},
    )
    request_id = created.json()["id"]
    assert created.json()["status"] == "manual"
    option = await client.post(
        f"/v1/travel-requests/{request_id}/options",
        json={
            "origin": "MCT",
            "destination": "COK",
            "airlineCode": "6E",
            "flightNumber": "6E45",
            "amountMinor": 9900,
            "currency": "OMR",
        },
    )
    body = {"optionId": option.json()["id"], "supplierReference": "MANUAL1"}
    headers = {"Idempotency-Key": "manual-1"}
    first = await client.post(f"/v1/travel-requests/{request_id}/confirm", headers=headers, json=body)
    second = await client.post(f"/v1/travel-requests/{request_id}/confirm", headers=headers, json=body)
    assert first.status_code == 200
    assert first.json()["status"] == "confirmed"
    assert first.json()["confirmationMode"] == "manual"
    assert second.json() == first.json()
    changed = await client.post(
        f"/v1/travel-requests/{request_id}/confirm",
        headers=headers,
        json={**body, "supplierReference": "OTHER"},
    )
    assert changed.status_code == 409
    assert changed.json()["code"] == "IDEMPOTENCY_CONFLICT"


async def test_notifications_email_and_sms(api, monkeypatch):
    client, app = api
    sent: list[str] = []

    async def fake_send(message, **kwargs):
        sent.append(message)

    monkeypatch.setattr("app.modules.notify.adapters.aiosmtplib.send", fake_send)
    email = await client.post(
        "/v1/notifications",
        headers={"Idempotency-Key": "mail-1"},
        json={
            "channel": "email",
            "templateKey": "case.opened",
            "to": "patient@example.com",
            "variables": {"caseRef": "CASE-2026-00041", "link": "https://example.com/cases/1"},
        },
    )
    assert email.status_code == 202
    otp = await client.post(
        "/v1/sms/otp",
        headers={"Idempotency-Key": "otp-1"},
        json={"phoneE164": "+96891234567", "code": "123456"},
    )
    assert otp.status_code == 202
    assert "123456" not in otp.text
    await process_once(app.state.session_factory, app.state.settings, app.state.http)
    assert sent
    assert "CASE-2026-00041" in sent[0]
    assert "diagnosis" not in sent[0].lower()
    saved = await client.get(f"/v1/notifications/{otp.json()['notificationId']}")
    assert saved.json()["status"] == "sent"
    assert "123456" in saved.json()["body"]

    disabled = await client.patch("/v1/notification-providers/log", json={"enabled": False})
    assert disabled.json()["enabled"] is False
    blocked = await client.post(
        "/v1/sms/otp",
        headers={"Idempotency-Key": "otp-2"},
        json={"phoneE164": "+96891234567", "code": "654321"},
    )
    assert blocked.status_code == 422
    assert blocked.json()["code"] == "PROVIDER_DISABLED"


async def test_notification_retry_after_failure(api, monkeypatch):
    client, app = api

    async def fail_send(message, **kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr("app.modules.notify.adapters.aiosmtplib.send", fail_send)
    created = await client.post(
        "/v1/notifications",
        headers={"Idempotency-Key": "mail-fail"},
        json={
            "channel": "email",
            "templateKey": "quote.published",
            "to": "patient@example.com",
            "variables": {"caseRef": "CASE-2026-00042", "link": "https://example.com/q"},
        },
    )
    await process_once(app.state.session_factory, app.state.settings, app.state.http)
    failed = await client.get(f"/v1/notifications/{created.json()['id']}")
    assert failed.json()["status"] == "failed"

    async def ok_send(message, **kwargs):
        return None

    monkeypatch.setattr("app.modules.notify.adapters.aiosmtplib.send", ok_send)
    retried = await client.post(f"/v1/notifications/{created.json()['id']}/retry")
    assert retried.json()["status"] == "pending"
    await process_once(app.state.session_factory, app.state.settings, app.state.http)
    sent = await client.get(f"/v1/notifications/{created.json()['id']}")
    assert sent.json()["status"] == "sent"

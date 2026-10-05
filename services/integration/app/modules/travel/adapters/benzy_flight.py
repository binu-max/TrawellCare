import asyncio
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tc_common import RuleFailed, UpstreamError, UpstreamUnavailable

from app.modules.travel.adapters import benzy_paths as paths
from app.modules.travel.adapters.normalize import (
    age_years,
    cancel_trips,
    first_pnr,
    is_completed,
    is_ok,
    load_offer_ref,
    offers_from_search,
    upstream_message,
)
from app.modules.travel.adapters.types import (
    BookResult,
    Contact,
    FlightSearch,
    NormalizedOffer,
    Passenger,
    PollResult,
    PricedOffer,
)
from app.modules.travel.models import TravelCall
from app.modules.travel.money import to_minor
from app.modules.travel.redact import redact, shrink
from app.modules.vendors.models import Vendor, VendorToken

logger = logging.getLogger("trawellcare.benzy")

TOKEN_TTL = timedelta(hours=47)
SEARCH_POLLS = 12
SEARCH_PAUSE_SECONDS = 2


def load_secrets(prefix: str) -> dict[str, str]:
    def read(suffix: str) -> str:
        return os.environ.get(f"{prefix}_{suffix}", "")

    return {
        "apiKey": read("API_KEY"),
        "password": read("PASSWORD"),
        "browserKey": read("BROWSER_KEY"),
        "key": read("KEY"),
    }


class BenzyFlightAdapter:
    code = "benzy_flight"

    def __init__(
        self,
        *,
        vendor: Vendor,
        http: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        session: AsyncSession,
    ):
        self.vendor = vendor
        self.http = http
        self.session_factory = session_factory
        self.session = session
        self.config = vendor.config or {}
        self.secrets = load_secrets(vendor.secret_prefix) if vendor.secret_prefix else {}
        self._token = ""
        self._client_id = ""

    async def search(self, query: FlightSearch, *, request_id: UUID) -> list[NormalizedOffer]:
        client_id, _token = await self._authorized_client()
        body = self._search_body(query, client_id)
        started = await self._post(
            "express_search",
            self._flight_url(paths.EXPRESS_SEARCH),
            body,
            request_id=request_id,
        )
        search_tui = str(started.get("TUI") or "")
        if not search_tui:
            raise UpstreamError("ExpressSearch did not return a TUI")
        payload = started
        for _ in range(SEARCH_POLLS):
            payload = await self._post(
                "get_exp_search",
                self._flight_url(paths.GET_EXP_SEARCH),
                {"ClientID": client_id, "TUI": search_tui},
                request_id=request_id,
            )
            if payload.get("TUI"):
                search_tui = str(payload["TUI"])
            if is_completed(payload.get("Completed")):
                break
            await self._pause()
        offers = offers_from_search(payload, query)
        if not offers and not is_completed(payload.get("Completed")):
            raise UpstreamError("Flight search did not finish and returned no options")
        return offers

    async def price(self, offer_ref: str, session_state: dict, *, request_id: UUID) -> PricedOffer:
        client_id, _token = await self._authorized_client()
        ref = load_offer_ref(offer_ref)
        currency = str(session_state.get("currency") or "INR")
        smart = await self._post(
            "smart_pricer",
            self._flight_url(paths.SMART_PRICER),
            {
                "Trips": [
                    {
                        "Amount": ref["netFare"],
                        "Index": ref["index"],
                        "OrderID": ref.get("orderId") or 1,
                        "TUI": ref["searchTui"],
                    }
                ],
                "ClientID": client_id,
                "Mode": "AS",
                "Options": "",
                "Source": "SF",
                "TripType": session_state.get("tripType") or "ON",
            },
            request_id=request_id,
        )
        price_tui = str(smart.get("TUI") or ref["searchTui"])
        priced = await self._post(
            "get_spricer",
            self._flight_url(paths.GET_SPRICER),
            {"TUI": price_tui},
            request_id=request_id,
        )
        if priced.get("TUI"):
            price_tui = str(priced["TUI"])
        net = priced.get("NetAmount")
        if net is None:
            net = smart.get("NetAmount", ref["netFare"])
        updated = {
            **session_state,
            "clientId": client_id,
            "priceTui": price_tui,
            "netAmount": net,
            "currency": str(priced.get("CurrencyCode") or currency),
            "tripType": session_state.get("tripType") or "ON",
        }
        money_currency = updated["currency"]
        return PricedOffer(
            amount_minor=to_minor(net, money_currency),
            currency=money_currency.upper(),
            supplier_session=updated,
            raw=priced,
        )

    async def book(
        self,
        *,
        offer_ref: str,
        session_state: dict,
        contact: Contact,
        passengers: list[Passenger],
        request_id: UUID,
    ) -> BookResult:
        client_id, _token = await self._authorized_client()
        price_tui = session_state.get("priceTui")
        net = session_state.get("netAmount")
        if not price_tui or net is None:
            raise RuleFailed("Price the selected option before confirming", code="PRICE_REQUIRED")
        created = await self._post(
            "create_itinerary",
            self._flight_url(paths.CREATE_ITINERARY),
            self._itinerary_body(price_tui, net, client_id, contact, passengers),
            request_id=request_id,
        )
        transaction_id = created.get("TransactionID")
        itinerary_tui = str(created.get("TUI") or price_tui)
        net_amount = created.get("NetAmount", net)
        if transaction_id is None:
            raise UpstreamError("CreateItinerary did not return a transaction id")
        started = await self._post(
            "start_pay",
            self._flight_url(paths.START_PAY),
            self._start_pay_body(transaction_id, net_amount, client_id, itinerary_tui),
            request_id=request_id,
        )
        state = {
            **session_state,
            "clientId": client_id,
            "transactionId": transaction_id,
            "itineraryTui": str(started.get("TUI") or itinerary_tui),
            "netAmount": net_amount,
            "bookStatus": started.get("BookStatus"),
        }
        pnr = first_pnr(started)
        if pnr:
            state["supplierReference"] = pnr
            return BookResult(
                status="confirmed",
                supplier_reference=pnr,
                supplier_session=state,
                amount_minor=to_minor(net_amount, state.get("currency") or "INR"),
                currency=str(state.get("currency") or "INR").upper(),
            )
        return BookResult(
            status="confirming",
            supplier_reference=None,
            supplier_session=state,
            amount_minor=to_minor(net_amount, state.get("currency") or "INR"),
            currency=str(state.get("currency") or "INR").upper(),
        )

    async def poll(self, session_state: dict, *, request_id: UUID) -> PollResult:
        client_id, _token = await self._authorized_client()
        tui = session_state.get("itineraryTui")
        transaction_id = session_state.get("transactionId")
        status = await self._post(
            "itinerary_status",
            self._flight_url(paths.ITINERARY_STATUS),
            {"TUI": tui, "TransactionID": transaction_id},
            request_id=request_id,
        )
        current = str(status.get("CurrentStatus") or "")
        if current.lower() == "failed":
            return PollResult(
                done=True,
                success=False,
                supplier_reference=None,
                supplier_session=session_state,
                error=upstream_message(status),
            )
        if current.lower() != "success":
            return PollResult(
                done=False,
                success=False,
                supplier_reference=None,
                supplier_session=session_state,
            )
        retrieved = await self._post(
            "retrieve_booking",
            self._flight_url(paths.RETRIEVE_BOOKING),
            {
                "TUI": tui or "",
                "ClientID": client_id,
                "ReferenceNumber": str(transaction_id),
                "ReferenceType": "T",
                "ServiceType": "FLT",
            },
            request_id=request_id,
        )
        pnr = first_pnr(retrieved)
        state = {**session_state, "retrieve": retrieved, "supplierReference": pnr}
        return PollResult(
            done=True,
            success=True,
            supplier_reference=pnr,
            supplier_session=state,
        )

    async def cancel(self, session_state: dict, *, remarks: str, request_id: UUID) -> dict:
        client_id, _token = await self._authorized_client()
        retrieve = session_state.get("retrieve") or {}
        trips = cancel_trips(retrieve)
        if not trips:
            raise RuleFailed(
                "This booking has no passenger identifiers to cancel yet.",
                code="CANCEL_NOT_READY",
            )
        return await self._post(
            "cancel",
            self._flight_url(paths.CANCEL),
            {
                "ClientID": client_id,
                "ClientIP": "",
                "Remarks": remarks or "Cancelled by trawellcare",
                "TUI": session_state.get("itineraryTui") or "",
                "TransactionID": session_state.get("transactionId"),
                "Trips": trips,
            },
            request_id=request_id,
        )

    def _search_body(self, query: FlightSearch, client_id: str) -> dict:
        fare_type = "RT" if query.return_date else "ON"
        trip = {
            "From": query.origin.upper(),
            "To": query.destination.upper(),
            "ReturnDate": query.return_date or "",
            "OnwardDate": query.depart_date,
            "TUI": "",
        }
        body = {
            "FareType": fare_type,
            "ADT": query.adults,
            "CHD": query.children,
            "INF": query.infants,
            "Cabin": query.cabin,
            "Source": "CF",
            "Mode": "AS",
            "ClientID": client_id,
            "IsMultipleCarrier": False,
            "IsRefundable": False,
            "preferedAirlines": None,
            "TUI": "",
            "SecType": "",
            "Trips": [trip],
            "Parameters": {
                "Airlines": "",
                "GroupType": "",
                "Refundable": "",
                "IsDirect": query.direct_only,
                "IsStudentFare": False,
                "IsNearbyAirport": False,
                "IsExtendedSearch": "false",
            },
        }
        channel = self.config.get("channelId")
        if channel:
            body["ChannelID"] = channel
        return body

    def _itinerary_body(
        self,
        tui: str,
        net_amount,
        client_id: str,
        contact: Contact,
        passengers: list[Passenger],
    ) -> dict:
        travellers = []
        for index, passenger in enumerate(passengers, start=1):
            travellers.append(
                {
                    "ID": index,
                    "Title": passenger.title,
                    "FName": passenger.first_name,
                    "LName": passenger.last_name,
                    "Age": age_years(passenger.date_of_birth),
                    "DOB": passenger.date_of_birth,
                    "Gender": passenger.gender,
                    "PTC": passenger.passenger_type,
                    "Nationality": passenger.nationality,
                    "PassportNo": passenger.passport_number,
                    "PLI": passenger.passport_issued_city,
                    "PDOE": passenger.passport_expiry,
                    "VisaType": passenger.visa_type,
                }
            )
        digits = "".join(ch for ch in contact.mobile if ch.isdigit())
        return {
            "TUI": tui,
            "ContactInfo": {
                "Title": "",
                "FName": contact.first_name,
                "LName": contact.last_name,
                "Mobile": digits,
                "Phone": "",
                "Email": contact.email,
                "Address": contact.address,
                "CountryCode": contact.country_code,
                "MobileCountryCode": contact.mobile_country_code,
                "State": contact.state,
                "City": contact.city,
                "PIN": contact.pin,
                "GSTCompanyName": "",
                "GSTTIN": "",
                "GSTMobile": "",
                "GSTEmail": "",
                "UpdateProfile": False,
                "IsGuest": False,
            },
            "Travellers": travellers,
            "PLP": [],
            "SSR": [],
            "CrossSell": [],
            "NetAmount": net_amount,
            "SSRAmount": 0,
            "ClientID": client_id,
            "DeviceID": "",
            "AppVersion": "",
            "CrossSellAmount": 0,
        }

    def _start_pay_body(self, transaction_id, net_amount, client_id: str, tui: str) -> dict:
        return {
            "TransactionID": transaction_id,
            "PaymentAmount": 0,
            "NetAmount": net_amount,
            "BrowserKey": self.secrets.get("browserKey") or "",
            "ClientID": client_id,
            "TUI": tui,
            "Hold": False,
            "Promo": None,
            "PaymentType": "",
            "BankCode": "",
            "GateWayCode": "",
            "MerchantID": "",
            "PaymentCharge": 0,
            "ReleaseDate": "",
            "OnlinePayment": False,
            "DepositPayment": True,
            "Card": {
                "Number": "",
                "Expiry": "",
                "CVV": "",
                "CHName": "",
                "Address": "",
                "City": "",
                "State": "",
                "Country": "",
                "PIN": "",
                "International": False,
                "SaveCard": False,
                "FName": "",
                "LName": "",
                "EMIMonths": "0",
            },
            "VPA": "",
            "CardAlias": "",
            "QuickPay": None,
            "RMSSignature": "",
            "TargetCurrency": "",
            "TargetAmount": 0,
            "ServiceType": "ITI",
        }

    async def _authorized_client(self) -> tuple[str, str]:
        self._require_secrets()
        now = datetime.now(UTC)
        if self._token and self._client_id:
            return self._client_id, self._token
        cached = await self.session.get(VendorToken, self.vendor.code)
        if cached and cached.expires_at > now and cached.token:
            self._token = cached.token
            self._client_id = cached.client_id
            return cached.client_id, cached.token
        signed = await self._post(
            "signature",
            self._utils_url(paths.SIGNATURE),
            self._signature_body(),
            request_id=None,
            authorize=False,
        )
        token = str(signed.get("Token") or "")
        client_id = str(signed.get("ClientID") or "")
        if not token:
            raise UpstreamError("Signature did not return a token")
        expires_at = now + TOKEN_TTL
        stmt = pg_insert(VendorToken).values(
            vendor_code=self.vendor.code,
            token=token,
            client_id=client_id,
            expires_at=expires_at,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[VendorToken.vendor_code],
            set_={
                "token": token,
                "client_id": client_id,
                "expires_at": expires_at,
                "updated_at": now,
            },
        )
        await self.session.execute(stmt)
        await self.session.flush()
        self._token = token
        self._client_id = client_id
        return client_id, token

    def _signature_body(self) -> dict:
        body = {
            "MerchantID": self.config.get("merchantId") or "",
            "ApiKey": self.secrets["apiKey"],
            "ClientID": self.config.get("clientId") or "",
            "Password": self.secrets["password"],
            "AgentCode": self.config.get("agentCode") or "",
            "BrowserKey": self.secrets.get("browserKey") or "",
        }
        if self.secrets.get("key"):
            body["Key"] = self.secrets["key"]
        return body

    def _require_secrets(self) -> None:
        if not self.secrets.get("apiKey") or not self.secrets.get("password"):
            raise RuleFailed(
                f"Credentials for vendor {self.vendor.code} are not configured",
                code="VENDOR_NOT_CONFIGURED",
            )

    def _flight_url(self, path: str) -> str:
        base = str(self.config.get("flightBaseUrl") or "").rstrip("/")
        return f"{base}{path}"

    def _utils_url(self, path: str) -> str:
        base = str(self.config.get("utilsBaseUrl") or "").rstrip("/")
        return f"{base}{path}"

    async def _bearer(self) -> str:
        _client, token = await self._authorized_client()
        return token

    async def _post(
        self,
        operation: str,
        url: str,
        body: dict,
        *,
        request_id: UUID | None,
        authorize: bool = True,
    ) -> dict:
        headers = {"Content-Type": "application/json"}
        if authorize:
            headers["Authorization"] = f"Bearer {self._token}"
        started = time.perf_counter()
        try:
            response = await self.http.post(url, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            await self._record(operation, None, started, body, {"error": "timeout"}, request_id)
            raise UpstreamUnavailable("Travel vendor timed out") from exc
        except httpx.HTTPError as exc:
            await self._record(operation, None, started, body, {"error": "unavailable"}, request_id)
            raise UpstreamUnavailable("Travel vendor is unavailable") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text[:500]}
        if not isinstance(payload, dict):
            payload = {"raw": payload}
        await self._record(operation, response.status_code, latency_ms, body, payload, request_id, from_seconds=False)
        if response.status_code >= 500:
            raise UpstreamUnavailable(upstream_message(payload))
        if response.status_code >= 400 or not is_ok(payload):
            raise UpstreamError(upstream_message(payload))
        logger.info("vendor call %s status=%s latency_ms=%s", operation, response.status_code, latency_ms)
        return payload

    async def _record(
        self,
        operation: str,
        http_status: int | None,
        started_or_latency,
        body: dict,
        payload: dict,
        request_id: UUID | None,
        from_seconds: bool = True,
    ) -> None:
        latency_ms = (
            int((time.perf_counter() - started_or_latency) * 1000) if from_seconds else int(started_or_latency)
        )
        async with self.session_factory() as audit:
            audit.add(
                TravelCall(
                    travel_request_id=request_id,
                    vendor_code=self.vendor.code,
                    operation=operation,
                    http_status=http_status,
                    latency_ms=latency_ms,
                    request_body=redact(body),
                    response_body=redact(shrink(payload)),
                )
            )
            await audit.commit()

    async def _pause(self) -> None:
        await asyncio.sleep(SEARCH_PAUSE_SECONDS)

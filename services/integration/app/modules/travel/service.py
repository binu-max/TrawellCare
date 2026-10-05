import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tc_common import NotFound, RuleFailed, ValidationFailed

from app.backoff import MAX_ATTEMPTS, next_attempt_at
from app.idempotency import complete, reserve
from app.modules.travel.adapters.normalize import cabin_code
from app.modules.travel.adapters.types import Contact, FlightSearch, Passenger
from app.modules.travel.factory import build_travel_adapter
from app.modules.travel.models import TravelOption, TravelRequest
from app.modules.travel.repository import TravelRepository
from app.modules.travel.schemas import (
    CancelBody,
    ConfirmBody,
    ContactBody,
    CreateTravelRequest,
    ManualOptionBody,
    OptionList,
    OptionView,
    PassengerBody,
    PriceBody,
    SearchCriteria,
    TravelRequestView,
)
from app.modules.vendors.service import VendorService


def request_view(row: TravelRequest) -> TravelRequestView:
    return TravelRequestView(
        id=row.id,
        case_id=row.case_id,
        booking_id=row.booking_id,
        vendor_code=row.vendor_code,
        product=row.product,
        status=row.status,
        supplier_reference=row.supplier_reference,
        amount_minor=row.amount_minor,
        currency=row.currency,
        confirmation_mode=row.confirmation_mode,
        error_code=row.error_code,
        search=row.search_criteria or {},
    )


def option_view(row: TravelOption) -> OptionView:
    return OptionView(
        id=row.id,
        origin=row.origin,
        destination=row.destination,
        depart_at=row.depart_at,
        arrive_at=row.arrive_at,
        airline_code=row.airline_code,
        flight_number=row.flight_number,
        stops=row.stops,
        cabin=row.cabin,
        amount_minor=row.amount_minor,
        currency=row.currency,
    )


class TravelService:
    def __init__(
        self,
        repo: TravelRepository,
        vendors: VendorService,
        *,
        http: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ):
        self.repo = repo
        self.vendors = vendors
        self.http = http
        self.session_factory = session_factory

    async def create(self, case_id: uuid.UUID, body: CreateTravelRequest) -> TravelRequestView:
        if body.product != "flight":
            raise ValidationFailed("Only flight travel requests are supported")
        vendor = await self.vendors.resolve(body.vendor_code, body.product)
        status = "manual" if vendor.adapter_type == "manual" else "draft"
        row = TravelRequest(
            case_id=case_id,
            booking_id=body.booking_id,
            vendor_code=vendor.code,
            product=body.product,
            status=status,
            search_criteria=body.search.model_dump(mode="json", by_alias=True) if body.search else {},
            supplier_session={"tripType": "RT" if body.search and body.search.return_date else "ON"},
        )
        await self.repo.add(row)
        return request_view(row)

    async def get(self, request_id: uuid.UUID) -> TravelRequestView:
        return request_view(await self._require(request_id))

    async def list_options(self, request_id: uuid.UUID) -> OptionList:
        await self._require(request_id)
        options = await self.repo.options(request_id)
        return OptionList(options=[option_view(option) for option in options])

    async def search(self, request_id: uuid.UUID, body: SearchCriteria | None) -> OptionList:
        row = await self._require(request_id)
        criteria = body or self._criteria_from_row(row)
        if criteria is None:
            raise ValidationFailed("Search criteria are required")
        row.search_criteria = criteria.model_dump(mode="json", by_alias=True)
        row.supplier_session = {**(row.supplier_session or {}), "tripType": "RT" if criteria.return_date else "ON"}
        vendor = await self.vendors.require(row.vendor_code)
        adapter = self._adapter(vendor)
        query = self._query(criteria)
        row.status = "searching"
        await self.repo.session.flush()
        offers = await adapter.search(query, request_id=row.id)
        options = [
            TravelOption(
                travel_request_id=row.id,
                supplier_offer_ref=offer.supplier_offer_ref,
                origin=offer.origin,
                destination=offer.destination,
                depart_at=offer.depart_at,
                arrive_at=offer.arrive_at,
                airline_code=offer.airline_code,
                flight_number=offer.flight_number,
                stops=offer.stops,
                cabin=criteria.cabin,
                amount_minor=offer.amount_minor,
                currency=offer.currency,
                raw=offer.raw,
            )
            for offer in offers
        ]
        await self.repo.replace_options(row.id, options)
        row.status = "options_ready"
        row.supplier_session = {**(row.supplier_session or {}), "currency": options[0].currency if options else None}
        await self.repo.session.flush()
        return OptionList(options=[option_view(option) for option in options])

    async def add_option(self, request_id: uuid.UUID, body: ManualOptionBody) -> OptionView:
        row = await self._require(request_id)
        option = TravelOption(
            travel_request_id=row.id,
            supplier_offer_ref="",
            origin=body.origin.upper(),
            destination=body.destination.upper(),
            depart_at=body.depart_at,
            arrive_at=body.arrive_at,
            airline_code=body.airline_code,
            flight_number=body.flight_number,
            stops=body.stops,
            cabin=body.cabin,
            amount_minor=body.amount_minor,
            currency=body.currency.upper(),
            raw={"source": "manual"},
        )
        self.repo.session.add(option)
        row.status = "options_ready"
        row.amount_minor = body.amount_minor
        row.currency = body.currency.upper()
        await self.repo.session.flush()
        return option_view(option)

    async def price(self, request_id: uuid.UUID, body: PriceBody) -> TravelRequestView:
        row = await self._require(request_id)
        option = await self.repo.option(request_id, body.option_id)
        if option is None:
            raise NotFound("Travel option not found")
        vendor = await self.vendors.require(row.vendor_code)
        if vendor.adapter_type == "manual":
            row.status = "priced"
            row.amount_minor = option.amount_minor
            row.currency = option.currency
            row.supplier_session = {**(row.supplier_session or {}), "optionId": str(option.id)}
            await self.repo.session.flush()
            return request_view(row)
        adapter = self._adapter(vendor)
        priced = await adapter.price(option.supplier_offer_ref, row.supplier_session or {}, request_id=row.id)
        option.amount_minor = priced.amount_minor
        option.currency = priced.currency
        row.amount_minor = priced.amount_minor
        row.currency = priced.currency
        row.status = "priced"
        row.supplier_session = {**priced.supplier_session, "optionId": str(option.id)}
        await self.repo.session.flush()
        return request_view(row)

    async def confirm(
        self,
        request_id: uuid.UUID,
        body: ConfirmBody,
        *,
        idempotency_key: str,
    ) -> TravelRequestView | dict:
        payload = body.model_dump(mode="json", by_alias=True)
        payload["requestId"] = str(request_id)
        replay = await reserve(self.repo.session, idempotency_key, payload)
        if replay is not None:
            return replay
        row = await self._require(request_id)
        if body.supplier_reference:
            row.supplier_reference = body.supplier_reference
            row.status = "confirmed"
            row.confirmation_mode = "manual"
            if body.option_id:
                row.supplier_session = {**(row.supplier_session or {}), "optionId": str(body.option_id)}
            await self.repo.session.flush()
            view = request_view(row)
            dumped = view.model_dump(mode="json", by_alias=True)
            await complete(self.repo.session, idempotency_key, 200, dumped)
            return view
        if body.option_id is None or body.contact is None or not body.passengers:
            raise ValidationFailed("Live confirm needs optionId, contact, and passengers")
        option = await self.repo.option(request_id, body.option_id)
        if option is None:
            raise NotFound("Travel option not found")
        vendor = await self.vendors.require(row.vendor_code)
        adapter = self._adapter(vendor)
        booked = await adapter.book(
            offer_ref=option.supplier_offer_ref,
            session_state=row.supplier_session or {},
            contact=self._contact(body.contact),
            passengers=[self._passenger(item) for item in body.passengers],
            request_id=row.id,
        )
        row.status = booked.status
        row.supplier_reference = booked.supplier_reference
        row.supplier_session = booked.supplier_session
        row.amount_minor = booked.amount_minor
        row.currency = booked.currency
        row.confirmation_mode = "live"
        row.attempts = 0
        row.next_attempt_at = None
        row.error_code = None
        await self.repo.session.flush()
        view = request_view(row)
        await complete(self.repo.session, idempotency_key, 200, view.model_dump(mode="json", by_alias=True))
        return view

    async def cancel(self, request_id: uuid.UUID, body: CancelBody) -> TravelRequestView:
        row = await self._require(request_id)
        if row.confirmation_mode == "manual" or row.vendor_code == "manual":
            row.status = "cancelled"
            await self.repo.session.flush()
            return request_view(row)
        vendor = await self.vendors.require(row.vendor_code)
        adapter = self._adapter(vendor)
        await adapter.cancel(row.supplier_session or {}, remarks=body.remarks, request_id=row.id)
        row.status = "cancelled"
        await self.repo.session.flush()
        return request_view(row)

    async def poll_confirmations(self) -> int:
        rows = await self.repo.due_confirmations()
        processed = 0
        for row in rows:
            vendor = await self.vendors.repo.get(row.vendor_code)
            if vendor is None or not vendor.enabled:
                row.status = "failed"
                row.error_code = "VENDOR_DISABLED"
                row.last_error = "Vendor is disabled"
                continue
            adapter = self._adapter(vendor)
            try:
                result = await adapter.poll(row.supplier_session or {}, request_id=row.id)
            except Exception as exc:
                self._schedule_retry(row, str(exc))
                processed += 1
                continue
            if not result.done:
                self._schedule_retry(row, "Booking is still in progress")
            elif not result.success:
                row.status = "failed"
                row.error_code = "UPSTREAM_ERROR"
                row.last_error = (result.error or "Booking failed")[:500]
            else:
                row.status = "confirmed"
                row.supplier_reference = result.supplier_reference
                row.supplier_session = result.supplier_session
                row.last_error = None
                row.error_code = None
            processed += 1
        await self.repo.session.flush()
        return processed

    def _schedule_retry(self, row: TravelRequest, error: str) -> None:
        row.attempts += 1
        row.last_error = error[:500]
        if row.attempts >= MAX_ATTEMPTS:
            row.status = "failed"
            row.error_code = "ATTEMPTS_EXCEEDED"
            return
        row.next_attempt_at = next_attempt_at(row.attempts)

    def _adapter(self, vendor):
        return build_travel_adapter(
            vendor,
            http=self.http,
            session_factory=self.session_factory,
            session=self.repo.session,
        )

    async def _require(self, request_id: uuid.UUID) -> TravelRequest:
        row = await self.repo.get(request_id)
        if row is None:
            raise NotFound("Travel request not found")
        return row

    def _criteria_from_row(self, row: TravelRequest) -> SearchCriteria | None:
        raw = row.search_criteria or {}
        if not raw:
            return None
        return SearchCriteria.model_validate(raw)

    def _query(self, criteria: SearchCriteria) -> FlightSearch:
        try:
            cabin = cabin_code(criteria.cabin)
        except ValueError as exc:
            raise ValidationFailed(str(exc)) from exc
        return FlightSearch(
            origin=criteria.origin.upper(),
            destination=criteria.destination.upper(),
            depart_date=criteria.depart_date,
            return_date=criteria.return_date,
            adults=criteria.adults,
            children=criteria.children,
            infants=criteria.infants,
            cabin=cabin,
            direct_only=criteria.direct_only,
        )

    def _contact(self, body: ContactBody) -> Contact:
        return Contact(
            first_name=body.first_name,
            last_name=body.last_name,
            email=body.email,
            mobile=body.mobile,
            country_code=body.country_code,
            mobile_country_code=body.mobile_country_code,
            address=body.address,
            city=body.city,
            state=body.state,
            pin=body.pin,
        )

    def _passenger(self, body: PassengerBody) -> Passenger:
        return Passenger(
            title=body.title,
            first_name=body.first_name,
            last_name=body.last_name,
            date_of_birth=body.date_of_birth,
            gender=body.gender,
            passenger_type=body.passenger_type,
            nationality=body.nationality,
            passport_number=body.passport_number,
            passport_expiry=body.passport_expiry,
            passport_issued_city=body.passport_issued_city,
            visa_type=body.visa_type,
        )

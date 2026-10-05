from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class FlightSearch:
    origin: str
    destination: str
    depart_date: str
    return_date: str | None = None
    adults: int = 1
    children: int = 0
    infants: int = 0
    cabin: str = "E"
    direct_only: bool = False


@dataclass
class NormalizedOffer:
    supplier_offer_ref: str
    origin: str
    destination: str
    depart_at: datetime | None
    arrive_at: datetime | None
    airline_code: str
    flight_number: str
    stops: int
    cabin: str
    amount_minor: int
    currency: str
    raw: dict = field(default_factory=dict)


@dataclass
class Passenger:
    title: str
    first_name: str
    last_name: str
    date_of_birth: str
    gender: str
    passenger_type: str = "ADT"
    nationality: str = ""
    passport_number: str = ""
    passport_expiry: str = ""
    passport_issued_city: str = ""
    visa_type: str = ""


@dataclass
class Contact:
    first_name: str
    last_name: str
    email: str
    mobile: str
    country_code: str = "OM"
    mobile_country_code: str = "+968"
    address: str = ""
    city: str = ""
    state: str = ""
    pin: str = ""


@dataclass
class PricedOffer:
    amount_minor: int
    currency: str
    supplier_session: dict
    raw: dict = field(default_factory=dict)


@dataclass
class BookResult:
    status: str
    supplier_reference: str | None
    supplier_session: dict
    amount_minor: int | None = None
    currency: str | None = None


@dataclass
class PollResult:
    done: bool
    success: bool
    supplier_reference: str | None
    supplier_session: dict
    error: str | None = None


class TravelPort(Protocol):
    code: str

    async def search(self, query: FlightSearch, *, request_id) -> list[NormalizedOffer]: ...

    async def price(self, offer_ref: str, session_state: dict, *, request_id) -> PricedOffer: ...

    async def book(
        self,
        *,
        offer_ref: str,
        session_state: dict,
        contact: Contact,
        passengers: list[Passenger],
        request_id,
    ) -> BookResult: ...

    async def poll(self, session_state: dict, *, request_id) -> PollResult: ...

    async def cancel(self, session_state: dict, *, remarks: str, request_id) -> dict: ...

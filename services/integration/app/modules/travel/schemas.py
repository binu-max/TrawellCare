from datetime import datetime
from uuid import UUID

from app.api_models import APIModel


class SearchCriteria(APIModel):
    origin: str
    destination: str
    depart_date: str
    return_date: str | None = None
    adults: int = 1
    children: int = 0
    infants: int = 0
    cabin: str = "economy"
    direct_only: bool = False


class CreateTravelRequest(APIModel):
    vendor_code: str | None = None
    product: str = "flight"
    booking_id: UUID | None = None
    search: SearchCriteria | None = None


class ManualOptionBody(APIModel):
    origin: str
    destination: str
    depart_at: datetime | None = None
    arrive_at: datetime | None = None
    airline_code: str = ""
    flight_number: str = ""
    stops: int = 0
    cabin: str = "economy"
    amount_minor: int
    currency: str


class PriceBody(APIModel):
    option_id: UUID


class PassengerBody(APIModel):
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


class ContactBody(APIModel):
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


class ConfirmBody(APIModel):
    option_id: UUID | None = None
    supplier_reference: str | None = None
    contact: ContactBody | None = None
    passengers: list[PassengerBody] = []


class CancelBody(APIModel):
    remarks: str = ""


class OptionView(APIModel):
    id: UUID
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


class TravelRequestView(APIModel):
    id: UUID
    case_id: UUID
    booking_id: UUID | None
    vendor_code: str
    product: str
    status: str
    supplier_reference: str | None
    amount_minor: int | None
    currency: str | None
    confirmation_mode: str | None
    error_code: str | None
    search: dict


class OptionList(APIModel):
    options: list[OptionView]

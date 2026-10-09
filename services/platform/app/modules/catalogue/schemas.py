from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.api_models import APIModel


class HospitalBody(APIModel):
    name_en: str
    name_ar: str = ""
    country: str
    city: str
    accreditation: str | None = None
    rating: Decimal = Decimal("0")


class HospitalView(HospitalBody):
    id: UUID
    active: bool


class DoctorBody(APIModel):
    name_en: str
    name_ar: str = ""
    specialty: str
    user_id: UUID | None = None
    hospital_id: UUID | None = None


class DoctorView(APIModel):
    id: UUID
    name_en: str
    name_ar: str
    specialty: str
    user_id: UUID | None
    active: bool


class ProcedureBody(APIModel):
    slug: str
    specialty: str
    name_en: str
    name_ar: str = ""
    hospital_id: UUID | None = None


class ProcedureView(APIModel):
    id: UUID
    slug: str
    specialty: str
    name_en: str
    name_ar: str
    active: bool


class PackageComponentIn(APIModel):
    module_type: str
    description: str = ""


class PackageBody(APIModel):
    name_en: str
    name_ar: str = ""
    hospital_id: UUID | None = None
    components: list[PackageComponentIn] = []


class PackageView(APIModel):
    id: UUID
    name_en: str
    name_ar: str
    hospital_id: UUID | None
    active: bool


class ActivePatch(APIModel):
    active: bool


class TariffBody(APIModel):
    hospital_id: UUID | None = None
    procedure_id: UUID | None = None
    package_id: UUID | None = None
    currency: str
    amount_minor: int
    valid_from: datetime | None = None


class TariffView(APIModel):
    id: UUID
    hospital_id: UUID | None
    procedure_id: UUID | None
    package_id: UUID | None
    currency: str
    amount_minor: int
    valid_from: datetime
    valid_to: datetime | None

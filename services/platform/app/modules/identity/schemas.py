from datetime import date, datetime
from uuid import UUID

from app.api_models import APIModel


class PhoneStart(APIModel):
    phone_e164: str
    locale: str = "en"
    purpose: str = "login"


class PhoneStartResult(APIModel):
    challenge_id: UUID
    expires_at: datetime


class PhoneVerify(APIModel):
    challenge_id: UUID
    code: str


class TokenResult(APIModel):
    access_token: str
    refresh_token: str
    customer_id: UUID | None = None


class SignoffVerifyResult(APIModel):
    verified: bool
    challenge_id: UUID


class PhoneResend(APIModel):
    challenge_id: UUID


class RefreshBody(APIModel):
    refresh_token: str


class CustomerPatch(APIModel):
    display_name: str | None = None
    country: str | None = None
    locale: str | None = None
    timezone: str | None = None


class CustomerView(APIModel):
    id: UUID
    display_name: str
    phone: str | None
    locale: str
    timezone: str
    country: str | None = None


class CompanionBody(APIModel):
    display_name: str
    relationship: str
    date_of_birth: date | None = None
    nationality: str | None = None


class CompanionPatch(APIModel):
    display_name: str | None = None
    relationship: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None


class CompanionView(APIModel):
    id: UUID
    display_name: str
    relationship: str
    date_of_birth: date | None
    nationality: str | None


class ConsentBody(APIModel):
    purpose: str
    text_version: str
    channel: str = "web"


class ConsentView(APIModel):
    id: UUID
    purpose: str
    text_version: str
    granted_at: datetime
    withdrawn_at: datetime | None
    channel: str


class RegisterEmail(APIModel):
    email: str
    password: str


class VerifyEmail(APIModel):
    challenge_id: UUID
    code: str


class EmailLogin(APIModel):
    email: str
    password: str


class StaffLogin(APIModel):
    email: str
    password: str


class MfaToken(APIModel):
    mfa_token: str


class StaffTotp(APIModel):
    mfa_token: str
    code: str


class StaffToken(APIModel):
    access_token: str
    refresh_token: str

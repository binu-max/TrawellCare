import hashlib
import re
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tc_common import Conflict, NotFound, RuleFailed, Unauthenticated, UpstreamError, UpstreamUnavailable

from app.actor import Actor
from app.events import audit
from app.modules.engagement.models import Referral
from app.modules.identity.models import (
    Companion,
    Consent,
    Customer,
    EmailChallenge,
    OtpChallenge,
    PhoneIdentity,
    RefreshToken,
    Role,
    StaffProfile,
    TotpSecret,
    User,
    UserRole,
)
from app.modules.identity.schemas import (
    CompanionBody,
    CompanionPatch,
    CompanionView,
    ConsentBody,
    ConsentView,
    CustomerPatch,
    CustomerView,
    EmailLogin,
    MfaToken,
    PhoneStart,
    PhoneStartResult,
    PhoneVerify,
    RegisterEmail,
    SignoffVerifyResult,
    StaffLogin,
    StaffToken,
    StaffTotp,
    TokenResult,
    VerifyEmail,
)
from app.security import (
    generate_otp_code,
    hash_otp,
    hash_password,
    hash_token,
    issue_access_token,
    new_refresh_token,
    otp_matches,
    password_matches,
    totp_matches,
)
from app.settings import Settings

_PHONE = re.compile(r"^\+[1-9][0-9]{7,14}$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _phone_hash(phone: str) -> str:
    return hashlib.sha256(phone.encode()).hexdigest()


def assert_phone(phone: str) -> str:
    if not _PHONE.match(phone):
        raise RuleFailed("Phone must be E.164", code="VALIDATION_FAILED", status=400)
    return phone


async def _deliver_sms(http: httpx.AsyncClient, settings: Settings, phone: str, code: str, locale: str) -> None:
    if settings.otp_delivery == "log":
        return
    try:
        response = await http.post(
            f"{settings.integration_base_url.rstrip('/')}/v1/sms/otp",
            headers={
                "X-Api-Key": settings.integration_api_key,
                "Idempotency-Key": str(hash_token(f"{phone}:{code}:{_utcnow().timestamp()}")),
            },
            json={"phoneE164": phone, "code": code, "locale": locale},
        )
    except httpx.HTTPError as exc:
        raise UpstreamUnavailable("SMS provider unavailable") from exc
    if response.status_code >= 500:
        raise UpstreamUnavailable("SMS provider unavailable")
    if response.status_code >= 400:
        raise UpstreamError("SMS provider rejected the message")


async def _rate_limit(session: AsyncSession, phone_hash: str, ip: str | None) -> None:
    now = _utcnow()
    hour_ago = now - timedelta(hours=1)
    phone_count = await session.scalar(
        select(func.count())
        .select_from(OtpChallenge)
        .where(OtpChallenge.phone_hash == phone_hash, OtpChallenge.created_at >= hour_ago)
    )
    if phone_count and phone_count >= 5:
        raise RuleFailed("Too many codes for this phone", code="RATE_LIMITED")
    if ip:
        ip_count = await session.scalar(
            select(func.count())
            .select_from(OtpChallenge)
            .where(OtpChallenge.ip == ip, OtpChallenge.created_at >= hour_ago)
        )
        if ip_count and ip_count >= 20:
            raise RuleFailed("Too many codes from this network", code="RATE_LIMITED")


async def start_phone(
    session: AsyncSession,
    http: httpx.AsyncClient,
    settings: Settings,
    body: PhoneStart,
    *,
    ip: str | None,
    actor: Actor | None,
) -> PhoneStartResult:
    if body.purpose not in ("login", "signoff"):
        raise RuleFailed("Purpose must be login or signoff", code="VALIDATION_FAILED", status=400)
    if body.purpose == "signoff" and (actor is None or actor.kind != "customer"):
        raise Unauthenticated("Sign-off codes require a customer session")
    phone = assert_phone(body.phone_e164)
    phone_hash = _phone_hash(phone)
    await _rate_limit(session, phone_hash, ip)
    now = _utcnow()
    latest = await session.scalar(
        select(OtpChallenge)
        .where(
            OtpChallenge.phone_hash == phone_hash,
            OtpChallenge.purpose == body.purpose,
            OtpChallenge.consumed_at.is_(None),
        )
        .order_by(OtpChallenge.created_at.desc())
    )
    if latest and latest.created_at and (now - latest.created_at).total_seconds() < 60:
        raise RuleFailed("Wait before requesting another code", code="RATE_LIMITED")
    if latest and latest.consumed_at is None:
        latest.consumed_at = now
    code = generate_otp_code()
    challenge = OtpChallenge(
        phone_hash=phone_hash,
        phone_e164=phone,
        purpose=body.purpose,
        code_hash=hash_otp(settings.otp_pepper, code),
        expires_at=now + timedelta(minutes=5),
        ip=ip,
    )
    session.add(challenge)
    await session.flush()
    await _deliver_sms(http, settings, phone, code, body.locale)
    return PhoneStartResult(challenge_id=challenge.id, expires_at=challenge.expires_at)


async def resend_phone(
    session: AsyncSession,
    http: httpx.AsyncClient,
    settings: Settings,
    challenge_id,
    *,
    ip: str | None,
    actor: Actor | None,
) -> PhoneStartResult:
    challenge = await session.get(OtpChallenge, challenge_id)
    if challenge is None or not challenge.phone_e164:
        raise Unauthenticated("Invalid code")
    phone = challenge.phone_e164
    return await start_phone(
        session,
        http,
        settings,
        PhoneStart(phone_e164=phone, purpose=challenge.purpose),
        ip=ip,
        actor=actor,
    )


async def _issue_refresh(session: AsyncSession, user: User, kind: str, settings: Settings) -> str:
    token = new_refresh_token()
    if kind == "staff":
        expires = _utcnow() + timedelta(hours=settings.staff_refresh_hours)
    else:
        expires = _utcnow() + timedelta(days=settings.customer_refresh_days)
    session.add(RefreshToken(user_id=user.id, token_hash=hash_token(token), kind=kind, expires_at=expires))
    return token


async def _roles_for(session: AsyncSession, user_id) -> list[str]:
    rows = await session.scalars(
        select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
    )
    return list(rows)


async def verify_phone(
    session: AsyncSession,
    settings: Settings,
    private_key: str,
    body: PhoneVerify,
    *,
    referral_code: str | None = None,
) -> TokenResult | SignoffVerifyResult:
    challenge = await session.get(OtpChallenge, body.challenge_id)
    if challenge is None or challenge.consumed_at is not None:
        raise Unauthenticated("Invalid code")
    now = _utcnow()
    if challenge.expires_at < now:
        raise RuleFailed("Code expired", code="OTP_EXPIRED")
    if challenge.attempts >= 3:
        raise RuleFailed("Too many attempts", code="OTP_ATTEMPTS_EXCEEDED")
    if not otp_matches(settings.otp_pepper, body.code, challenge.code_hash):
        challenge.attempts += 1
        if challenge.attempts >= 3:
            challenge.consumed_at = now
            raise RuleFailed("Too many attempts", code="OTP_ATTEMPTS_EXCEEDED")
        raise Unauthenticated("Invalid code")
    if challenge.purpose == "signoff":
        challenge.verified_at = now
        return SignoffVerifyResult(verified=True, challenge_id=challenge.id)

    challenge.consumed_at = now
    identity = await session.scalar(select(PhoneIdentity).where(PhoneIdentity.phone_hash == challenge.phone_hash))
    if identity is None:
        user = User(status="active")
        session.add(user)
        await session.flush()
        identity = PhoneIdentity(
            user_id=user.id,
            phone_e164=challenge.phone_e164,
            phone_hash=challenge.phone_hash,
            verified_at=now,
            is_primary=True,
        )
        session.add(identity)
        customer = Customer(user_id=user.id, locale="en")
        session.add(customer)
        await session.flush()
        audit(session, entity_type="customer", entity_id=customer.id, action="created", to_status="active")
        if referral_code:
            referral = await session.scalar(
                select(Referral).where(Referral.code == referral_code, Referral.status == "open")
            )
            if referral and referral.referrer_customer_id != customer.id:
                referral.referred_customer_id = customer.id
                referral.status = "converted"
    else:
        user = await session.get(User, identity.user_id)
        if user is None or user.status != "active":
            raise Unauthenticated("Invalid code")
        customer = await session.scalar(select(Customer).where(Customer.user_id == user.id))
        if customer is None:
            raise Unauthenticated("Invalid code")
        identity.verified_at = now
        if not identity.phone_e164:
            identity.phone_e164 = challenge.phone_e164
    refresh = await _issue_refresh(session, user, "customer", settings)
    actor = Actor(id=user.id, kind="customer", roles=["customer"], customer_id=customer.id)
    access = issue_access_token(actor, private_key, minutes=settings.access_token_minutes)
    return TokenResult(access_token=access, refresh_token=refresh, customer_id=customer.id)


async def store_phone_on_identity(session: AsyncSession, phone: str, phone_hash: str) -> None:
    identity = await session.scalar(select(PhoneIdentity).where(PhoneIdentity.phone_hash == phone_hash))
    if identity and not identity.phone_e164:
        identity.phone_e164 = phone


async def refresh_session(
    session: AsyncSession,
    settings: Settings,
    private_key: str,
    raw_token: str,
) -> TokenResult | StaffToken:
    now = _utcnow()
    row = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if row is None:
        raise Unauthenticated("Invalid refresh token")
    if row.revoked_at is not None:
        others = await session.scalars(select(RefreshToken).where(RefreshToken.user_id == row.user_id))
        for token in others:
            token.revoked_at = now
        raise Unauthenticated("Refresh token revoked")
    if row.expires_at < now:
        raise Unauthenticated("Refresh token expired")
    user = await session.get(User, row.user_id)
    if user is None or user.status != "active":
        raise Unauthenticated("Invalid refresh token")
    row.revoked_at = now
    refresh = await _issue_refresh(session, user, row.kind, settings)
    if row.kind == "staff":
        roles = await _roles_for(session, user.id)
        actor = Actor(id=user.id, kind="staff", roles=roles)
        access = issue_access_token(actor, private_key, minutes=settings.access_token_minutes)
        return StaffToken(access_token=access, refresh_token=refresh)
    customer = await session.scalar(select(Customer).where(Customer.user_id == user.id))
    actor = Actor(
        id=user.id,
        kind="customer",
        roles=["customer"],
        customer_id=customer.id if customer else None,
    )
    access = issue_access_token(actor, private_key, minutes=settings.access_token_minutes)
    return TokenResult(
        access_token=access,
        refresh_token=refresh,
        customer_id=customer.id if customer else None,
    )


async def logout(session: AsyncSession, user_id) -> None:
    now = _utcnow()
    rows = await session.scalars(select(RefreshToken).where(RefreshToken.user_id == user_id))
    for row in rows:
        if row.revoked_at is None:
            row.revoked_at = now


async def customer_me(session: AsyncSession, actor: Actor) -> CustomerView:
    customer = await session.get(Customer, actor.customer_id)
    if customer is None:
        raise NotFound("Customer not found")
    phone = await session.scalar(
        select(PhoneIdentity.phone_e164).where(PhoneIdentity.user_id == customer.user_id, PhoneIdentity.is_primary.is_(True))
    )
    return CustomerView(
        id=customer.id,
        display_name=customer.display_name,
        phone=phone,
        locale=customer.locale,
        timezone=customer.timezone,
        country=customer.country,
    )


async def patch_customer(session: AsyncSession, actor: Actor, body: CustomerPatch) -> CustomerView:
    customer = await session.get(Customer, actor.customer_id)
    if customer is None:
        raise NotFound("Customer not found")
    for field in ("display_name", "country", "locale", "timezone"):
        value = getattr(body, field)
        if value is not None:
            setattr(customer, field, value)
    return await customer_me(session, actor)


async def list_companions(session: AsyncSession, actor: Actor) -> list[CompanionView]:
    rows = await session.scalars(select(Companion).where(Companion.customer_id == actor.customer_id))
    return [
        CompanionView(
            id=row.id,
            display_name=row.display_name,
            relationship=row.relationship,
            date_of_birth=row.date_of_birth,
            nationality=row.nationality,
        )
        for row in rows
    ]


async def add_companion(session: AsyncSession, actor: Actor, body: CompanionBody) -> CompanionView:
    row = Companion(
        customer_id=actor.customer_id,
        display_name=body.display_name,
        relationship=body.relationship,
        date_of_birth=body.date_of_birth,
        nationality=body.nationality,
    )
    session.add(row)
    await session.flush()
    return CompanionView(
        id=row.id,
        display_name=row.display_name,
        relationship=row.relationship,
        date_of_birth=row.date_of_birth,
        nationality=row.nationality,
    )


async def patch_companion(session: AsyncSession, actor: Actor, companion_id, body: CompanionPatch) -> CompanionView:
    row = await session.get(Companion, companion_id)
    if row is None or row.customer_id != actor.customer_id:
        raise NotFound("Companion not found")
    for field in ("display_name", "relationship", "date_of_birth", "nationality"):
        value = getattr(body, field)
        if value is not None:
            setattr(row, field, value)
    return CompanionView(
        id=row.id,
        display_name=row.display_name,
        relationship=row.relationship,
        date_of_birth=row.date_of_birth,
        nationality=row.nationality,
    )


async def grant_consent(session: AsyncSession, actor: Actor, body: ConsentBody, ip: str | None) -> ConsentView:
    row = Consent(
        customer_id=actor.customer_id,
        purpose=body.purpose,
        text_version=body.text_version,
        granted_at=_utcnow(),
        channel=body.channel,
        ip=ip,
    )
    session.add(row)
    await session.flush()
    return ConsentView(
        id=row.id,
        purpose=row.purpose,
        text_version=row.text_version,
        granted_at=row.granted_at,
        withdrawn_at=None,
        channel=row.channel,
    )


async def withdraw_consent(session: AsyncSession, actor: Actor, consent_id) -> ConsentView:
    row = await session.get(Consent, consent_id)
    if row is None or row.customer_id != actor.customer_id:
        raise NotFound("Consent not found")
    if row.withdrawn_at is None:
        row.withdrawn_at = _utcnow()
    return ConsentView(
        id=row.id,
        purpose=row.purpose,
        text_version=row.text_version,
        granted_at=row.granted_at,
        withdrawn_at=row.withdrawn_at,
        channel=row.channel,
    )


async def register_email(
    session: AsyncSession,
    settings: Settings,
    actor: Actor,
    body: RegisterEmail,
) -> dict:
    user = await session.get(User, actor.id)
    if user is None:
        raise NotFound("User not found")
    taken = await session.scalar(select(User).where(User.email == body.email, User.id != user.id))
    if taken:
        raise Conflict("Email is already in use")
    user.email = body.email
    user.password_hash = hash_password(body.password)
    user.email_verified_at = None
    code = generate_otp_code()
    challenge = EmailChallenge(
        user_id=user.id,
        email=body.email,
        code_hash=hash_otp(settings.otp_pepper, code),
        expires_at=_utcnow() + timedelta(minutes=30),
    )
    session.add(challenge)
    await session.flush()
    if settings.otp_delivery != "log":
        return {"challengeId": str(challenge.id)}
    return {"challengeId": str(challenge.id)}


async def verify_email(session: AsyncSession, settings: Settings, actor: Actor, body: VerifyEmail) -> dict:
    challenge = await session.get(EmailChallenge, body.challenge_id)
    if challenge is None or challenge.user_id != actor.id or challenge.consumed_at is not None:
        raise Unauthenticated("Invalid code")
    if challenge.expires_at < _utcnow():
        raise RuleFailed("Code expired", code="OTP_EXPIRED")
    if not otp_matches(settings.otp_pepper, body.code, challenge.code_hash):
        raise Unauthenticated("Invalid code")
    challenge.consumed_at = _utcnow()
    user = await session.get(User, actor.id)
    if user:
        user.email_verified_at = _utcnow()
    return {"status": "verified"}


async def login_email(
    session: AsyncSession,
    settings: Settings,
    private_key: str,
    body: EmailLogin,
) -> TokenResult:
    user = await session.scalar(select(User).where(User.email == body.email))
    if user is None or user.status != "active" or user.email_verified_at is None:
        raise Unauthenticated("Invalid email or password")
    if not password_matches(body.password, user.password_hash):
        raise Unauthenticated("Invalid email or password")
    customer = await session.scalar(select(Customer).where(Customer.user_id == user.id))
    if customer is None:
        raise Unauthenticated("Invalid email or password")
    refresh = await _issue_refresh(session, user, "customer", settings)
    actor = Actor(id=user.id, kind="customer", roles=["customer"], customer_id=customer.id)
    access = issue_access_token(actor, private_key, minutes=settings.access_token_minutes)
    return TokenResult(access_token=access, refresh_token=refresh, customer_id=customer.id)


async def staff_login(session: AsyncSession, settings: Settings, private_key: str, body: StaffLogin) -> MfaToken:
    user = await session.scalar(select(User).where(User.email == body.email))
    if user is None or user.status != "active" or not password_matches(body.password, user.password_hash):
        raise Unauthenticated("Invalid email or password")
    secret = await session.scalar(select(TotpSecret).where(TotpSecret.user_id == user.id))
    if secret is None:
        raise Unauthenticated("Staff sign-in is not enrolled")
    actor = Actor(id=user.id, kind="mfa", roles=[])
    token = issue_access_token(actor, private_key, minutes=5, kind="mfa")
    return MfaToken(mfa_token=token)


async def staff_totp(
    session: AsyncSession,
    settings: Settings,
    private_key: str,
    public_key: str,
    body: StaffTotp,
) -> StaffToken:
    from app.security import actor_from_token

    actor = actor_from_token(body.mfa_token, public_key)
    if actor.kind != "mfa":
        raise Unauthenticated("Invalid sign-in step")
    secret = await session.scalar(select(TotpSecret).where(TotpSecret.user_id == actor.id))
    user = await session.get(User, actor.id)
    if secret is None or user is None or user.status != "active" or not totp_matches(secret.secret, body.code):
        raise Unauthenticated("Invalid authenticator code")
    if secret.confirmed_at is None:
        secret.confirmed_at = _utcnow()
    roles = await _roles_for(session, user.id)
    profile = await session.scalar(select(StaffProfile).where(StaffProfile.user_id == user.id))
    if profile is None:
        session.add(StaffProfile(user_id=user.id, display_name=user.email or "Staff"))
    refresh = await _issue_refresh(session, user, "staff", settings)
    staff = Actor(id=user.id, kind="staff", roles=roles)
    access = issue_access_token(staff, private_key, minutes=settings.access_token_minutes)
    return StaffToken(access_token=access, refresh_token=refresh)

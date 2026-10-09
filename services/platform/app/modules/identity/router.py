from fastapi import APIRouter, Depends, Query, Request

from app.deps import (
    CustomerDep,
    SessionDep,
    SettingsDep,
    UserDep,
    client_ip,
    get_http,
    optional_customer,
)
from app.http import dump
from app.modules.identity import service
from app.modules.identity.schemas import (
    CompanionBody,
    CompanionPatch,
    ConsentBody,
    CustomerPatch,
    EmailLogin,
    PhoneResend,
    PhoneStart,
    PhoneVerify,
    RefreshBody,
    RegisterEmail,
    StaffLogin,
    StaffTotp,
    VerifyEmail,
)

router = APIRouter(tags=["identity"])


@router.post("/v1/auth/phone/start")
async def phone_start(
    body: PhoneStart,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    actor=Depends(optional_customer),
    http=Depends(get_http),
):
    result = await service.start_phone(session, http, settings, body, ip=client_ip(request), actor=actor)
    return dump(result)


@router.post("/v1/auth/phone/verify")
async def phone_verify(
    body: PhoneVerify,
    session: SessionDep,
    settings: SettingsDep,
    request: Request,
    referral_code: str | None = Query(default=None, alias="referralCode"),
):
    result = await service.verify_phone(
        session,
        settings,
        request.app.state.private_key,
        body,
        referral_code=referral_code,
    )
    return dump(result)


@router.post("/v1/auth/phone/resend")
async def phone_resend(
    body: PhoneResend,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    actor=Depends(optional_customer),
    http=Depends(get_http),
):
    result = await service.resend_phone(
        session,
        http,
        settings,
        body.challenge_id,
        ip=client_ip(request),
        actor=actor,
    )
    return dump(result)


@router.post("/v1/auth/refresh")
async def refresh(body: RefreshBody, session: SessionDep, settings: SettingsDep, request: Request):
    result = await service.refresh_session(session, settings, request.app.state.private_key, body.refresh_token)
    return dump(result)


@router.post("/v1/auth/logout")
async def logout(actor: UserDep, session: SessionDep):
    await service.logout(session, actor.id)
    return {"status": "ok"}


@router.get("/v1/customers/me")
async def me(actor: CustomerDep, session: SessionDep):
    return dump(await service.customer_me(session, actor))


@router.patch("/v1/customers/me")
async def patch_me(body: CustomerPatch, actor: CustomerDep, session: SessionDep):
    return dump(await service.patch_customer(session, actor, body))


@router.get("/v1/customers/me/companions")
async def companions(actor: CustomerDep, session: SessionDep):
    return dump(await service.list_companions(session, actor))


@router.post("/v1/customers/me/companions", status_code=201)
async def add_companion(body: CompanionBody, actor: CustomerDep, session: SessionDep):
    return dump(await service.add_companion(session, actor, body))


@router.patch("/v1/customers/me/companions/{companion_id}")
async def patch_companion(companion_id: str, body: CompanionPatch, actor: CustomerDep, session: SessionDep):
    return dump(await service.patch_companion(session, actor, companion_id, body))


@router.post("/v1/customers/me/consents", status_code=201)
async def consent(body: ConsentBody, actor: CustomerDep, session: SessionDep, request: Request):
    return dump(await service.grant_consent(session, actor, body, client_ip(request)))


@router.post("/v1/customers/me/consents/{consent_id}/withdraw")
async def withdraw(consent_id: str, actor: CustomerDep, session: SessionDep):
    return dump(await service.withdraw_consent(session, actor, consent_id))


@router.post("/v1/auth/customer/register")
async def register(body: RegisterEmail, actor: CustomerDep, session: SessionDep, settings: SettingsDep):
    return await service.register_email(session, settings, actor, body)


@router.post("/v1/auth/customer/verify-email")
async def verify_email(body: VerifyEmail, actor: CustomerDep, session: SessionDep, settings: SettingsDep):
    return await service.verify_email(session, settings, actor, body)


@router.post("/v1/auth/customer/login")
async def email_login(body: EmailLogin, session: SessionDep, settings: SettingsDep, request: Request):
    return dump(await service.login_email(session, settings, request.app.state.private_key, body))


@router.post("/v1/auth/staff/login")
async def staff_login(body: StaffLogin, session: SessionDep, settings: SettingsDep, request: Request):
    return dump(await service.staff_login(session, settings, request.app.state.private_key, body))


@router.post("/v1/auth/staff/totp")
async def staff_totp(body: StaffTotp, session: SessionDep, settings: SettingsDep, request: Request):
    return dump(
        await service.staff_totp(
            session,
            settings,
            request.app.state.private_key,
            request.app.state.public_key,
            body,
        )
    )

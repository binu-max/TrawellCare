import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notify.models import NotificationProvider, NotificationTemplate
from app.modules.vendors.models import Vendor


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def akbar_config() -> dict:
    return {
        "merchantId": _env("VENDOR_AKBAR_MERCHANT_ID"),
        "clientId": _env("VENDOR_AKBAR_CLIENT_ID"),
        "agentCode": _env("VENDOR_AKBAR_AGENT_CODE"),
        "channelId": _env("VENDOR_AKBAR_CHANNEL_ID"),
        "flightBaseUrl": _env(
            "VENDOR_AKBAR_FLIGHT_BASE_URL",
            "https://b2bapiflights.benzyinfotech.com",
        ),
        "utilsBaseUrl": _env(
            "VENDOR_AKBAR_UTILS_BASE_URL",
            "https://b2bapiutils.benzyinfotech.com",
        ),
    }


async def seed(session: AsyncSession) -> None:
    if await session.scalar(select(Vendor.id).where(Vendor.code == "akbar")) is None:
        session.add(
            Vendor(
                code="akbar",
                display_name="Akbar Travels",
                adapter_type="benzy_flight",
                product="flight",
                enabled=True,
                config=akbar_config(),
                secret_prefix="VENDOR_AKBAR",
            )
        )
    if await session.scalar(select(Vendor.id).where(Vendor.code == "manual")) is None:
        session.add(
            Vendor(
                code="manual",
                display_name="Manual",
                adapter_type="manual",
                product="flight",
                enabled=True,
                config={},
                secret_prefix="",
            )
        )
    providers = [
        ("smtp", "email", "smtp", "SMTP (Mailpit or SendGrid)", True, {}),
        ("resend", "email", "resend", "Resend", False, {}),
        ("log", "sms", "log", "Log SMS", True, {}),
        ("twilio", "sms", "twilio", "Twilio", False, {}),
    ]
    for code, channel, adapter, name, enabled, config in providers:
        if await session.scalar(select(NotificationProvider.id).where(NotificationProvider.code == code)) is None:
            session.add(
                NotificationProvider(
                    code=code,
                    channel=channel,
                    adapter_type=adapter,
                    display_name=name,
                    enabled=enabled,
                    config=config,
                )
            )
    templates = [
        (
            "case.opened",
            "email",
            "en",
            "Your trawellcare request {caseRef}",
            "A coordinator will call you within four hours. Reference {caseRef}. {link}",
        ),
        (
            "consultation.booked",
            "email",
            "en",
            "Consultation booked {caseRef}",
            "Your consultation is scheduled. Reference {caseRef}. {link}",
        ),
        (
            "quote.published",
            "email",
            "en",
            "Your care plan is ready {caseRef}",
            "A plan is ready to review. Reference {caseRef}. {link}",
        ),
        (
            "otp.sms",
            "sms",
            "en",
            None,
            "Your trawellcare code is {code}. It expires in 5 minutes.",
        ),
        ("test.hello", "email", "en", "Hello", "hello world"),
    ]
    for key, channel, locale, subject, body in templates:
        row = await session.scalar(
            select(NotificationTemplate).where(
                NotificationTemplate.key == key,
                NotificationTemplate.channel == channel,
                NotificationTemplate.locale == locale,
            )
        )
        if row is None:
            session.add(
                NotificationTemplate(key=key, channel=channel, locale=locale, subject=subject, body=body)
            )
        elif key == "test.hello":
            row.subject = subject
            row.body = body
    await session.flush()

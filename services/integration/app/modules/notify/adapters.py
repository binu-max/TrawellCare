import logging
from typing import Protocol

import aiosmtplib
from tc_common import RuleFailed

from app.modules.notify.models import NotificationProvider
from app.settings import Settings

logger = logging.getLogger("trawellcare.notify")


class EmailPort(Protocol):
    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class SmsPort(Protocol):
    async def send(self, *, to: str, body: str) -> None: ...


class SmtpEmail:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def send(self, *, to: str, subject: str, body: str) -> None:
        message = (
            f"From: {self.settings.email_from}\r\n"
            f"To: {to}\r\n"
            f"Subject: {subject}\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            f"{body}"
        )
        kwargs: dict = {
            "hostname": self.settings.smtp_host,
            "port": self.settings.smtp_port,
            "sender": self.settings.email_from,
            "recipients": [to],
        }
        if self.settings.smtp_user:
            kwargs["username"] = self.settings.smtp_user
            kwargs["password"] = self.settings.smtp_login_password
        if self.settings.smtp_use_tls:
            kwargs["start_tls"] = True
        await aiosmtplib.send(message, **kwargs)


class LogSms:
    async def send(self, *, to: str, body: str) -> None:
        suffix = to[-4:] if len(to) >= 4 else "xxxx"
        logger.info("sms delivered to ***%s", suffix)


def build_sender(provider: NotificationProvider, settings: Settings):
    if provider.adapter_type == "smtp":
        return SmtpEmail(settings)
    if provider.adapter_type == "log":
        return LogSms()
    raise RuleFailed(
        f"Provider {provider.code} has no sender configured",
        code="PROVIDER_NOT_CONFIGURED",
    )

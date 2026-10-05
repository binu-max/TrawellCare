import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from tc_common import Conflict

from app.modules.control.models import IdempotencyKey

ACTOR = "integration"


def request_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


async def reserve(session: AsyncSession, key: str, payload: dict) -> dict | None:
    digest = request_hash(payload)
    existing = await session.scalar(
        select(IdempotencyKey).where(IdempotencyKey.actor_id == ACTOR, IdempotencyKey.key == key)
    )
    if existing:
        if existing.request_hash != digest:
            raise Conflict(
                "Idempotency key was reused with a different body",
                code="IDEMPOTENCY_CONFLICT",
            )
        if existing.response is None:
            raise Conflict(
                "A request with this idempotency key is already in progress",
                code="IDEMPOTENCY_CONFLICT",
            )
        return existing.response
    session.add(
        IdempotencyKey(
            actor_id=ACTOR,
            key=key,
            request_hash=digest,
            response=None,
            status_code=0,
        )
    )
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise Conflict(
            "A request with this idempotency key is already in progress",
            code="IDEMPOTENCY_CONFLICT",
        ) from exc
    return None


async def complete(session: AsyncSession, key: str, status_code: int, body: dict) -> None:
    row = await session.scalar(
        select(IdempotencyKey).where(IdempotencyKey.actor_id == ACTOR, IdempotencyKey.key == key)
    )
    if row is None:
        return
    row.status_code = status_code
    row.response = body

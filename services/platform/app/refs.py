from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.actor import SYSTEM_USER_ID, current_actor


async def next_ref(session: AsyncSession, name: str) -> str:
    year = datetime.now(timezone.utc).year
    actor = current_actor()
    actor_id = actor.id if actor else SYSTEM_USER_ID
    value = await session.scalar(
        text(
            """
            INSERT INTO platform.ref_counters
                (name, year, last_value, created_at, modified_at, created_by, modified_by)
            VALUES
                (:name, :year, 1, now(), now(), :actor, :actor)
            ON CONFLICT (name, year) DO UPDATE
            SET last_value = platform.ref_counters.last_value + 1,
                modified_at = now(),
                modified_by = :actor
            RETURNING last_value
            """
        ),
        {"name": name, "year": year, "actor": actor_id},
    )
    prefix = {"case": "CASE", "quote": "QT", "booking": "BK"}[name]
    return f"{prefix}-{year}-{int(value):05d}"

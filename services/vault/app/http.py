from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from tc_common.jwt import TokenActor

from app.idempotency import begin_command, finish_command


def dump(value):
    if isinstance(value, list):
        return [dump(item) for item in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    return value


async def command(
    session: AsyncSession,
    actor: TokenActor,
    key: str,
    payload: dict,
    status_code: int,
    producer,
):
    actor_key = f"{actor.kind}:{actor.id}"
    replay = await begin_command(session, actor_key, key, payload)
    if replay:
        await session.commit()
        return JSONResponse(status_code=replay["status"], content=replay["body"])
    body = dump(await producer())
    await finish_command(session, actor_key, key, status_code, body)
    await session.commit()
    return JSONResponse(status_code=status_code, content=body)

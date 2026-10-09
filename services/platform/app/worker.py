import asyncio
import logging

from app.db import build_database
from app.jobs import process_once
from app.seed import seed
from app.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("trawellcare.platform.worker")


async def main() -> None:
    settings = get_settings()
    engine, factory = build_database(settings.database_url)
    async with factory() as session:
        await seed(session, settings)
        await session.commit()
    logger.info("platform worker started")
    try:
        while True:
            await process_once(factory)
            await asyncio.sleep(settings.worker_interval_seconds)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import logging

import httpx

from app.db import build_database
from app.jobs import process_once
from app.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("trawellcare.worker")


async def main() -> None:
    settings = get_settings()
    engine, factory = build_database(settings.database_url)
    http = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0))
    logger.info("integration worker started")
    try:
        while True:
            await process_once(factory, settings, http)
            await asyncio.sleep(settings.worker_interval_seconds)
    finally:
        await http.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

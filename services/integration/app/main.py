import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from sqlalchemy import text
from tc_common.problem import install_problem_handlers

from app.db import build_database
from app.modules.notify.router import router as notify_router
from app.modules.travel.router import router as travel_router
from app.modules.vendors.router import router as vendor_router
from app.seed import seed
from app.settings import Settings, get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine, factory = build_database(app.state.settings.database_url)
        app.state.engine = engine
        app.state.session_factory = factory
        app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0))
        async with factory() as session:
            await seed(session)
            await session.commit()
        yield
        await app.state.http.aclose()
        await engine.dispose()

    app = FastAPI(title="trawellcare integration", version="0.1.0", lifespan=lifespan)
    app.state.settings = resolved
    install_problem_handlers(app)

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
            description=(
                "Travel vendors (Akbar/Benzy) and notifications. "
                "Protected routes need header **X-Api-Key** (same value as INTEGRATION_API_KEY)."
            ),
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {})["ApiKeyAuth"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-Api-Key",
        }
        for path, path_item in schema.get("paths", {}).items():
            if path in ("/health", "/ready"):
                continue
            for operation in path_item.values():
                if isinstance(operation, dict):
                    operation.setdefault("security", [{"ApiKeyAuth": []}])
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
    app.include_router(vendor_router)
    app.include_router(travel_router)
    app.include_router(notify_router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        async with app.state.session_factory() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


app = create_app()

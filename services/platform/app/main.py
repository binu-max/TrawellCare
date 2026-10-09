import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from sqlalchemy import text
from tc_common.problem import install_problem_handlers

from app.audit import install_audit_listener
from app.db import build_database
from app.modules.cases.router import router as cases_router
from app.modules.catalogue.router import router as catalogue_router
from app.modules.clinical.router import router as clinical_router
from app.modules.engagement.router import router as engagement_router
from app.modules.identity.router import router as identity_router
from app.modules.quotes.router import router as quotes_router
from app.security import generate_rsa_pem
from app.seed import seed
from app.settings import Settings, get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
install_audit_listener()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    if resolved.jwt_private_key and resolved.jwt_public_key:
        private_key, public_key = resolved.jwt_private_key, resolved.jwt_public_key
    else:
        private_key, public_key = generate_rsa_pem()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine, factory = build_database(app.state.settings.database_url)
        app.state.engine = engine
        app.state.session_factory = factory
        app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0))
        async with factory() as session:
            await seed(session, app.state.settings)
            await session.commit()
        yield
        await app.state.http.aclose()
        await engine.dispose()

    app = FastAPI(title="trawellcare platform", version="0.1.0", lifespan=lifespan)
    app.state.settings = resolved
    app.state.private_key = private_key
    app.state.public_key = public_key
    install_problem_handlers(app)

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
            description=(
                "Identity, cases, care plans, and quotes. "
                "Customer and staff routes use Authorization: Bearer. "
                "The chatbot handoff uses X-Api-Key."
            ),
        )
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
    app.include_router(identity_router)
    app.include_router(cases_router)
    app.include_router(catalogue_router)
    app.include_router(clinical_router)
    app.include_router(quotes_router)
    app.include_router(engagement_router)

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

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from sqlalchemy import text
from tc_common.problem import install_problem_handlers

from app.db import build_database, ping
from app.modules.documents.router import router as documents_router
from app.settings import Settings, get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def _ensure_jwt_public_key(settings: Settings) -> str:
    if settings.jwt_public_key.strip():
        return settings.jwt_public_key.strip()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    logging.warning("VAULT: JWT_PUBLIC_KEY not set; using ephemeral dev public key")
    return public.decode()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    public_key = _ensure_jwt_public_key(resolved)
    storage_root = Path(resolved.vault_storage_root)
    storage_root.mkdir(parents=True, exist_ok=True)

    from app.storage.local import LocalFilesystemStorage

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine, factory = build_database(resolved.database_url)
        app.state.engine = engine
        app.state.session_factory = factory
        app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0))
        yield
        await app.state.http.aclose()
        await engine.dispose()

    app = FastAPI(title="trawellcare vault", version="0.1.0", lifespan=lifespan)
    app.state.settings = resolved
    app.state.jwt_public_key = public_key
    app.state.storage = LocalFilesystemStorage(storage_root)
    install_problem_handlers(app)
    app.include_router(documents_router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        async with app.state.session_factory() as session:
            await ping(session)
        storage_root = Path(app.state.settings.vault_storage_root)
        if not storage_root.exists() or not storage_root.is_dir():
            return {"status": "degraded", "reason": "storage unavailable"}
        test = storage_root / ".write_probe"
        test.write_text("ok")
        test.unlink(missing_ok=True)
        return {"status": "ready"}

    return app


app = create_app()

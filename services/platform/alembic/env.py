import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.db import Base
from app.modules.cases import models as case_models  # noqa: F401
from app.modules.catalogue import models as catalogue_models  # noqa: F401
from app.modules.clinical import models as clinical_models  # noqa: F401
from app.modules.control import models as control_models  # noqa: F401
from app.modules.engagement import models as engagement_models  # noqa: F401
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.quotes import models as quote_models  # noqa: F401
from app.settings import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    raw = os.environ.get("DATABASE_URL") or get_settings().database_url
    return raw.replace("postgresql+asyncpg", "postgresql+psycopg")


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="alembic_version_platform",
        version_table_schema="platform",
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS platform"))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table="alembic_version_platform",
            version_table_schema="platform",
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

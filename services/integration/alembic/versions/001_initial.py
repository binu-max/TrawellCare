"""integration schema

Revision ID: 001_initial
Revises:
Create Date: 2026-10-05
"""

from alembic import op

from app.db import Base
from app.modules.control import models as control_models  # noqa: F401
from app.modules.notify import models as notify_models  # noqa: F401
from app.modules.travel import models as travel_models  # noqa: F401
from app.modules.vendors import models as vendor_models  # noqa: F401

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS integration")
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
    op.execute("DROP SCHEMA IF EXISTS integration CASCADE")

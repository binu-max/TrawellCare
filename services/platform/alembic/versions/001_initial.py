"""platform schema

Revision ID: 001_initial
Revises:
Create Date: 2026-10-09
"""

from alembic import op

from app.db import Base
from app.modules.cases import models as case_models  # noqa: F401
from app.modules.catalogue import models as catalogue_models  # noqa: F401
from app.modules.clinical import models as clinical_models  # noqa: F401
from app.modules.control import models as control_models  # noqa: F401
from app.modules.engagement import models as engagement_models  # noqa: F401
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.quotes import models as quote_models  # noqa: F401

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE SCHEMA IF NOT EXISTS platform")
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())

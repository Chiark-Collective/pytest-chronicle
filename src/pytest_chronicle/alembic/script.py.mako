"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from __future__ import annotations

from alembic import op  # type: ignore
import sqlalchemy as sa  # type: ignore

# revision identifiers, used by Alembic.
revision = "${up_revision}"
down_revision = ${down_revision | repr}
branch_labels = ${branch_labels | repr}
depends_on = ${depends_on | repr}


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

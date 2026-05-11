"""add election.reporting_pct for partial live tallies

Revision ID: f8e9d7c6b5a4
Revises: 899dc789c498
Create Date: 2026-05-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8e9d7c6b5a4"
down_revision: Union[str, Sequence[str], None] = "899dc789c498"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "elections",
        sa.Column("reporting_pct", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("elections", "reporting_pct")

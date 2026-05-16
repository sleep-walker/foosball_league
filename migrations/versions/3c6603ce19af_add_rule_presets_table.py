"""add rule_presets table

Revision ID: 3c6603ce19af
Revises: 851efb05ed34
Create Date: 2026-04-25 23:51:58.950080

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c6603ce19af'
down_revision: Union[str, None] = '851efb05ed34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'rule_presets',
        sa.Column('uuid', sa.Uuid(), nullable=False),
        sa.Column('league_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('rules', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['league_id'], ['leagues.uuid']),
        sa.PrimaryKeyConstraint('uuid'),
    )


def downgrade() -> None:
    op.drop_table('rule_presets')

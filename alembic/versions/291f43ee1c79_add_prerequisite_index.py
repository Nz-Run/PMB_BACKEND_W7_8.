"""add prerequisite index

Revision ID: 291f43ee1c79
Revises: 590d759d2bf2
Create Date: 2026-11-06 19:08:41.451642

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '291f43ee1c79'
down_revision: Union[str, Sequence[str], None] = '590d759d2bf2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_prasyarat_kode_prasyarat',
        'prasyarat',
        ['kode_prasyarat'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index(
        'ix_prasyarat_kode_prasyarat',
        table_name='prasyarat'
    )

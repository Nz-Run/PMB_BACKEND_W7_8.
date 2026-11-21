"""merge finance and billing migrations

Revision ID: b11afe8d64b7
Revises: 1c93a3ba6c6b, fb736b4b9a6d
Create Date: 2026-11-21 21:46:23.628946

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b11afe8d64b7'
down_revision: Union[str, Sequence[str], None] = ('1c93a3ba6c6b', 'fb736b4b9a6d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

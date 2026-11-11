
"""add krs needs review flag

Revision ID: 7d19c0bd14c6
Revises: 272f151ac75f
"""

from alembic import op
import sqlalchemy as sa

revision = '7d19c0bd14c6'
down_revision = '272f151ac75f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'krs',
        sa.Column(
            'needs_review',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false()
        )
    )


def downgrade() -> None:
    op.drop_column('krs', 'needs_review')

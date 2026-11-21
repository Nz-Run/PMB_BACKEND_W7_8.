"""Skip duplicate billing and payment tables migration.

Revision ID: 1c93a3ba6c6b
Revises: 173f8e224ede
"""

from typing import Sequence, Union


revision: str = "1c93a3ba6c6b"
down_revision: Union[str, Sequence[str], None] = "173f8e224ede"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Tables are already created by the finance migration."""
    pass


def downgrade() -> None:
    """No operation to reverse."""
    pass
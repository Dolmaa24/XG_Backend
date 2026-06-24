"""initial schema

Revision ID: 09aab70d90b1
Revises: 7d917e9a7496
Create Date: 2026-06-24 16:51:53.766340

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '09aab70d90b1'
down_revision: Union[str, Sequence[str], None] = '7d917e9a7496'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

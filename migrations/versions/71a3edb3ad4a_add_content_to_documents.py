"""add content to documents

Revision ID: 71a3edb3ad4a
Revises: b45b7dc84387
Create Date: 2026-10-22 22:41:51.645797

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '71a3edb3ad4a'
down_revision: Union[str, Sequence[str], None] = 'b45b7dc84387'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NOT NULL with no default would fail on any table that already has rows.
    # Add it with a temporary empty default so existing rows are filled, then
    # drop the default so every NEW row must supply real content.
    op.add_column('documents', sa.Column('content', sa.Text(), nullable=False, server_default=''))
    op.alter_column('documents', 'content', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documents', 'content')
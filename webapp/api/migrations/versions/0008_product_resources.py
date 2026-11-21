"""product resources: a note on each file (what it is, how to use it), and document / reference kinds

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('product_files', sa.Column('note', sa.String(length=500), server_default='', nullable=False))


def downgrade() -> None:
    op.drop_column('product_files', 'note')

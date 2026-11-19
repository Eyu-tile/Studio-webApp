"""job queues: media and agent jobs go to separate worker pools

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('queue', sa.String(length=20), server_default='media', nullable=False))
    op.execute("UPDATE jobs SET queue = 'agent' WHERE kind = 'agent_turn'")
    op.drop_index('ix_jobs_status_created', table_name='jobs')
    op.create_index('ix_jobs_queue_status_created', 'jobs', ['queue', 'status', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_jobs_queue_status_created', table_name='jobs')
    op.create_index('ix_jobs_status_created', 'jobs', ['status', 'created_at'], unique=False)
    op.drop_column('jobs', 'queue')

"""spend: a ledger per brand, a monthly Claude budget per brand, costs on approvals

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('spend_entries',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('brand_id', sa.UUID(), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('kind', sa.String(length=12), nullable=False),
    sa.Column('amount_usd', sa.Float(), nullable=False),
    sa.Column('job_id', sa.UUID(), nullable=True),
    sa.Column('thread_id', sa.UUID(), nullable=True),
    sa.Column('approval_id', sa.UUID(), nullable=True),
    sa.Column('note', sa.String(length=300), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['thread_id'], ['agent_threads.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['approval_id'], ['agent_approvals.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_spend_brand_provider_at', 'spend_entries', ['brand_id', 'provider', 'created_at'])
    op.create_index('ix_spend_entries_job_id', 'spend_entries', ['job_id'])
    op.add_column('brands', sa.Column('claude_budget_monthly', sa.Float(), nullable=True))
    op.add_column('agent_approvals', sa.Column('provider', sa.String(length=40), nullable=True))
    op.add_column('agent_approvals', sa.Column('cost_usd', sa.Float(), nullable=True))
    # what Claude already spent: each finished turn's reported cost, so this month's budget starts out right
    op.execute("""
        INSERT INTO spend_entries (id, brand_id, provider, kind, amount_usd, job_id, note, created_at)
        SELECT gen_random_uuid(), brand_id, 'anthropic', 'actual', (result->>'cost_usd')::float, id,
               'from the job history', COALESCE(finished_at, created_at)
        FROM jobs
        WHERE kind = 'agent_turn' AND result ? 'cost_usd' AND jsonb_typeof(result->'cost_usd') = 'number'
          AND (result->>'cost_usd')::float > 0
    """)


def downgrade() -> None:
    op.drop_column('agent_approvals', 'cost_usd')
    op.drop_column('agent_approvals', 'provider')
    op.drop_column('brands', 'claude_budget_monthly')
    op.drop_index('ix_spend_entries_job_id', table_name='spend_entries')
    op.drop_index('ix_spend_brand_provider_at', table_name='spend_entries')
    op.drop_table('spend_entries')

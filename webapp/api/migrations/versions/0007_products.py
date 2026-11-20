"""products: a client's products (card + packshots), and the product a project is for

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    op.create_table('products',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('brand_id', sa.UUID(), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('pitch', sa.String(length=500), nullable=False),
    sa.Column('benefits', JSON, nullable=False),
    sa.Column('claims_ok', JSON, nullable=False),
    sa.Column('claims_no', JSON, nullable=False),
    sa.Column('price', sa.String(length=120), nullable=False),
    sa.Column('links', JSON, nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('brand_id', 'slug')
    )
    op.create_index('ix_products_brand_id', 'products', ['brand_id'])
    op.create_table('product_files',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('product_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('filename', sa.String(length=400), nullable=False),
    sa.Column('mime', sa.String(length=200), nullable=False),
    sa.Column('size', sa.BigInteger(), nullable=False),
    sa.Column('storage_key', sa.String(length=800), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('storage_key')
    )
    op.create_index('ix_product_files_product_id', 'product_files', ['product_id'])
    op.add_column('projects', sa.Column('product_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_projects_product_id', 'projects', 'products', ['product_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_projects_product_id', 'projects', ['product_id'])


def downgrade() -> None:
    op.drop_index('ix_projects_product_id', table_name='projects')
    op.drop_constraint('fk_projects_product_id', 'projects', type_='foreignkey')
    op.drop_column('projects', 'product_id')
    op.drop_index('ix_product_files_product_id', table_name='product_files')
    op.drop_table('product_files')
    op.drop_index('ix_products_brand_id', table_name='products')
    op.drop_table('products')

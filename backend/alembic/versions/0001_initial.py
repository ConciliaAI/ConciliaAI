"""Tabelas iniciais de usuários e lotes.

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(80), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False))
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_table("batches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("total_documents", sa.Integer, nullable=False))


def downgrade():
    op.drop_table("batches")
    op.drop_index("ix_users_username", "users")
    op.drop_table("users")

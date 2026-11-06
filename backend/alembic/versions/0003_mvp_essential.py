"""MVP Essencial: grupos, divergências e trilha de revisão.
Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("document_groups",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_file_id", sa.Integer, sa.ForeignKey("source_files.id"), nullable=False),
        sa.Column("start_page", sa.Integer, nullable=False),
        sa.Column("end_page", sa.Integer, nullable=False),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("reasons", sa.JSON, nullable=False),
        sa.Column("fields", sa.JSON, nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("reviewed_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True))
    op.create_index("ix_document_groups_source_file_id", "document_groups", ["source_file_id"])
    op.create_table("findings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("batch_id", sa.Integer, sa.ForeignKey("batches.id"), nullable=False),
        sa.Column("invoice_id", sa.Integer, sa.ForeignKey("document_groups.id"), nullable=False),
        sa.Column("contract_id", sa.Integer, sa.ForeignKey("document_groups.id"), nullable=True),
        sa.Column("rule", sa.String(60), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(48), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("expected", sa.Text, nullable=True),
        sa.Column("observed", sa.Text, nullable=True),
        sa.Column("evidence", sa.JSON, nullable=False),
        sa.Column("resolution_note", sa.Text, nullable=True))
    op.create_index("ix_findings_batch_id", "findings", ["batch_id"])
    op.create_table("review_actions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("document_id", sa.Integer, sa.ForeignKey("document_groups.id"), nullable=False),
        sa.Column("reviewer_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("before", sa.JSON, nullable=False),
        sa.Column("after", sa.JSON, nullable=False),
        sa.Column("justification", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("review_actions")
    op.drop_index("ix_findings_batch_id", "findings")
    op.drop_table("findings")
    op.drop_index("ix_document_groups_source_file_id", "document_groups")
    op.drop_table("document_groups")

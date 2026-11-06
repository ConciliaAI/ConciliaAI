"""Arquivos de origem e OCR por página.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("source_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("batches.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(80), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("total_pages", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error", sa.Text(), nullable=True))
    op.create_index("ix_source_files_batch_id", "source_files", ["batch_id"])
    op.create_index("ix_source_files_sha256", "source_files", ["sha256"])
    op.create_table("pages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_file_id", sa.Integer(), sa.ForeignKey("source_files.id"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("ocr_method", sa.String(30), nullable=True),
        sa.Column("word_boxes", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.UniqueConstraint("source_file_id", "page_number", name="uq_source_file_page"))
    op.create_index("ix_pages_source_file_id", "pages", ["source_file_id"])


def downgrade():
    op.drop_index("ix_pages_source_file_id", "pages")
    op.drop_table("pages")
    op.drop_index("ix_source_files_sha256", "source_files")
    op.drop_index("ix_source_files_batch_id", "source_files")
    op.drop_table("source_files")

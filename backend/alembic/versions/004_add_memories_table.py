"""Add memories table with pgvector support.

Revision ID: 004
Revises: 003_foundation_upgrade
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = "004_add_memories"
down_revision = "003_foundation_upgrade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "memories",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("resident_id", sa.String(), sa.ForeignKey("residents.id"), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("related_resident_id", sa.String(), sa.ForeignKey("residents.id"), nullable=True),
        sa.Column("related_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("media_url", sa.Text(), nullable=True),
        sa.Column("media_summary", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Add pgvector column (can't be done through sa.Column easily)
    op.execute("ALTER TABLE memories ADD COLUMN embedding vector(1024)")

    # Indexes
    op.create_index("ix_memories_resident_type", "memories", ["resident_id", "type"])
    op.create_index("ix_memories_resident_related_resident", "memories", ["resident_id", "related_resident_id"])
    op.create_index("ix_memories_resident_related_user", "memories", ["resident_id", "related_user_id"])

    # HNSW index for fast vector similarity search
    op.execute("""
        CREATE INDEX ix_memories_embedding_hnsw
        ON memories USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)


def downgrade() -> None:
    op.drop_index("ix_memories_embedding_hnsw")
    op.drop_index("ix_memories_resident_related_user")
    op.drop_index("ix_memories_resident_related_resident")
    op.drop_index("ix_memories_resident_type")
    op.drop_table("memories")

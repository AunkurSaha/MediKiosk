"""patient evidence RAG search index

Revision ID: 7a3d9e1c5b20
Revises: 6f2b8c4d1a90
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.types import UserDefinedType

from alembic import op

revision: str = "7a3d9e1c5b20"
down_revision: Union[str, None] = "6f2b8c4d1a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


class VectorValue(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **_kw):
        return "VECTOR"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "rag_patient_chunks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_record_id", sa.String(), nullable=False),
        sa.Column("chunk_key", sa.String(length=160), nullable=False),
        sa.Column("document_id", sa.String(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=True),
        sa.Column("evidence_type", sa.String(length=40), nullable=False),
        sa.Column("verification_status", sa.String(length=40), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinician_verified", sa.Boolean(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("is_conflicted", sa.Boolean(), nullable=False),
        sa.Column("embedding", VectorValue(), nullable=True),
        sa.Column("embedding_provider", sa.String(length=80), nullable=True),
        sa.Column("embedding_model", sa.String(length=200), nullable=True),
        sa.Column("embedding_version", sa.String(length=80), nullable=True),
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
        sa.Column("content_checksum", sa.String(length=64), nullable=False),
        sa.Column("index_status", sa.String(length=20), nullable=False),
        sa.Column("index_error", sa.String(length=160), nullable=True),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "source_type",
            "source_record_id",
            "chunk_key",
            name="uq_rag_patient_chunk_source",
        ),
    )
    op.create_index("ix_rag_patient_chunks_patient_id", "rag_patient_chunks", ["patient_id"])
    op.create_index("ix_rag_patient_chunks_session_id", "rag_patient_chunks", ["session_id"])
    op.create_index("ix_rag_patient_chunks_document_id", "rag_patient_chunks", ["document_id"])
    op.create_index("ix_rag_patient_chunks_index_status", "rag_patient_chunks", ["index_status"])
    op.create_index(
        "ix_rag_patient_patient_session", "rag_patient_chunks", ["patient_id", "session_id"]
    )
    op.create_index(
        "ix_rag_patient_patient_verification",
        "rag_patient_chunks",
        ["patient_id", "verification_status"],
    )
    op.create_index(
        "ix_rag_patient_patient_source",
        "rag_patient_chunks",
        ["patient_id", "source_type"],
    )
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_rag_patient_text_fts ON rag_patient_chunks "
            "USING gin (to_tsvector('simple', text))"
        )
        op.execute(
            "CREATE INDEX ix_rag_patient_embedding_hnsw_2048 ON rag_patient_chunks "
            "USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops) "
            "WHERE embedding_dimension = 2048 AND index_status = 'indexed'"
        )


def downgrade() -> None:
    op.drop_table("rag_patient_chunks")

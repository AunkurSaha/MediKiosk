"""dual_provider_rag

Revision ID: 53d64d0dbe27
Revises: 7a3d9e1c5b20
Create Date: 2026-09-23 00:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '53d64d0dbe27'
down_revision = '7a3d9e1c5b20'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old unique constraint
    op.drop_constraint('uq_rag_patient_chunk_source', 'rag_patient_chunks', type_='unique')
    # Create new unique constraint including embedding provider info
    op.create_unique_constraint(
        'uq_rag_patient_chunk_source_representation',
        'rag_patient_chunks',
        ['source_type', 'source_record_id', 'chunk_key', 'embedding_provider', 'embedding_model', 'embedding_version']
    )


def downgrade() -> None:
    # Drop the new unique constraint
    op.drop_constraint('uq_rag_patient_chunk_source_representation', 'rag_patient_chunks', type_='unique')
    # Restore the old unique constraint
    op.create_unique_constraint(
        'uq_rag_patient_chunk_source',
        'rag_patient_chunks',
        ['source_type', 'source_record_id', 'chunk_key']
    )

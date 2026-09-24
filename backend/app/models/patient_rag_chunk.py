"""Patient-scoped RAG search index rows; canonical clinical tables remain authoritative."""

import json
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    text as sa_text,
)
from sqlalchemy.types import UserDefinedType

from app.database import Base


class VectorValue(UserDefinedType):
    """Portable pgvector column declaration with textual SQLite storage."""

    cache_ok = True

    def get_col_spec(self, **_kw):
        return "VECTOR"

    def bind_processor(self, _dialect):
        def process(value):
            if value is None or isinstance(value, str):
                return value
            return json.dumps([float(item) for item in value], separators=(",", ":"))

        return process

    def result_processor(self, _dialect, _coltype):
        def process(value):
            if value is None or isinstance(value, list):
                return value
            return [float(item) for item in json.loads(value)]

        return process


class HalfVector2048(VectorValue):
    """Fixed-size query type matching the production HNSW expression index."""

    cache_ok = True

    def get_col_spec(self, **_kw):
        return "HALFVEC(2048)"


class PatientRAGChunk(Base):
    __tablename__ = "rag_patient_chunks"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_record_id",
            "chunk_key",
            "embedding_provider",
            "embedding_model",
            "embedding_version",
            name="uq_rag_patient_chunk_source_representation",
        ),
        Index("ix_rag_patient_patient_session", "patient_id", "session_id"),
        Index("ix_rag_patient_patient_verification", "patient_id", "verification_status"),
        Index("ix_rag_patient_patient_source", "patient_id", "source_type"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_id = Column(
        String, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id = Column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source_type = Column(String(40), nullable=False)
    source_record_id = Column(String, nullable=False)
    chunk_key = Column(String(160), nullable=False)
    document_id = Column(
        String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    page_number = Column(Integer, nullable=True)
    text = Column(Text, nullable=False)
    normalized_text = Column(Text, nullable=True)
    evidence_type = Column(String(40), nullable=False, index=True)
    verification_status = Column(String(40), nullable=False, index=True)
    provenance_json = Column(JSON, nullable=False, default=dict)
    metadata_json = Column(JSON, nullable=False, default=dict)
    event_at = Column(DateTime(timezone=True), nullable=True, index=True)
    clinician_verified = Column(Boolean, nullable=False, default=False)
    is_current = Column(Boolean, nullable=False, default=True)
    is_conflicted = Column(Boolean, nullable=False, default=False)
    embedding = Column(VectorValue(), nullable=True)
    embedding_provider = Column(String(80), nullable=True)
    embedding_model = Column(String(200), nullable=True)
    embedding_version = Column(String(80), nullable=True)
    embedding_dimension = Column(Integer, nullable=True)
    content_checksum = Column(String(64), nullable=False)
    index_status = Column(String(20), nullable=False, default="pending", index=True)
    index_error = Column(String(160), nullable=True)
    last_indexed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=sa_text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(DateTime(timezone=True), nullable=True)

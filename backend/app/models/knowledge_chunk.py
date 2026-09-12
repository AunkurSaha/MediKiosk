"""SQLAlchemy model for knowledge chunks used in RAG."""

import uuid
from datetime import datetime, timezone
from json import dumps, loads

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database import Base


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # Source identification
    source_id = Column(String, nullable=False, index=True)
    source_title = Column(String, nullable=False)
    section = Column(String, nullable=False)
    # Content
    content = Column(Text, nullable=False)
    # Metadata
    topic = Column(String, nullable=False, index=True)  # e.g., chest_pain
    specialty = Column(String, nullable=True)
    language = Column(String, nullable=False, index=True)
    document_version = Column(String, nullable=False)
    source_reference = Column(String, nullable=True)
    # Checksum for change detection
    checksum = Column(String, nullable=False)
    # Embedding storage (as JSON string of list of floats)
    embedding_json = Column(Text, nullable=False)
    embedding_model = Column(String, nullable=False)
    embedding_provider = Column(String, nullable=True)
    embedding_dimension = Column(Integer, nullable=True)
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def get_embedding(self) -> list[float]:
        """Load the embedding from JSON storage."""
        return loads(self.embedding_json)

    def set_embedding(
        self,
        embedding: list[float],
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        """Store the embedding as JSON and record dimensionality and model provenance."""
        self.embedding_json = dumps(embedding)
        self.embedding_dimension = len(embedding)
        if provider is not None:
            self.embedding_provider = provider
        if model is not None:
            self.embedding_model = model

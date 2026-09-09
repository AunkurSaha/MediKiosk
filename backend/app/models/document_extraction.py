import uuid

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, String, Text, text
from sqlalchemy.orm import relationship

from app.database import Base


class DocumentExtraction(Base):
    __tablename__ = "document_extractions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    extractor = Column(String, nullable=False)
    extractor_version = Column(String, nullable=False)
    raw_text = Column(Text, nullable=True)
    structured_json = Column(JSON, nullable=False)
    confidence = Column(Float, nullable=True)
    verification_status = Column(String, nullable=False, server_default="unverified", index=True)
    verified_by = Column(String, nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verification_notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=text("CURRENT_TIMESTAMP"), nullable=True)

    document = relationship("Document", back_populates="extractions")

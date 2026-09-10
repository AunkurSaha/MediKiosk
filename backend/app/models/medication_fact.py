import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, text
from sqlalchemy.orm import relationship

from app.database import Base


class MedicationFact(Base):
    __tablename__ = "medication_fact"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_extraction_id = Column(
        String,
        ForeignKey("document_extractions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Medication details
    name = Column(String, nullable=False)
    dosage = Column(String, nullable=True)
    frequency = Column(String, nullable=True)
    route = Column(String, nullable=True)
    duration = Column(String, nullable=True)
    instructions = Column(String, nullable=True)
    # Source information
    source_text = Column(Text, nullable=True)  # original text from which this was extracted
    source_location = Column(String, nullable=True)  # e.g., page number or region if available
    # Verification status
    verification_status = Column(
        String, nullable=False, server_default="unverified", index=True
    )  # unverified, verified, rejected
    verified_by = Column(String, nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verification_notes = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
        index=True,
    )
    updated_at = Column(DateTime(timezone=True), onupdate=text("CURRENT_TIMESTAMP"), nullable=True)

    # Relationships
    session = relationship("Session", back_populates="medication_facts")
    document_extraction = relationship("DocumentExtraction", back_populates="medication_facts")

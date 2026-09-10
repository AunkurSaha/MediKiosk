import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text

from app.database import Base


class ClinicalSummary(Base):
    __tablename__ = "clinical_summaries"
    __table_args__ = (UniqueConstraint("session_id", name="uq_clinical_summaries_session"),)

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    generated_text = Column(Text, nullable=True)
    generated_structured_json = Column(Text, nullable=True)
    reviewed_text = Column(Text, nullable=True)
    confirmed_text = Column(Text, nullable=True)
    draft_provider = Column(String, default="deterministic", nullable=False)
    draft_version = Column(Integer, default=1, nullable=False)
    status = Column(String, nullable=False)  # e.g., 'generated', 'reviewed', 'confirmed'
    generated_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_by = Column(String, ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime(timezone=True), onupdate=text("CURRENT_TIMESTAMP"))

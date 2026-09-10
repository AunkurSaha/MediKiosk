import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class MedicalFactRevision(Base):
    __tablename__ = "medical_fact_revisions"
    __table_args__ = (
        UniqueConstraint("fact_type", "fact_id", "version", name="uq_fact_revision_version"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fact_type = Column(String, nullable=False)
    fact_id = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False)
    review_status = Column(String, nullable=False)
    original_data = Column(JSON, nullable=False)
    corrected_data = Column(JSON, nullable=True)
    reviewer_id = Column(String, ForeignKey("users.id"), nullable=False)
    review_notes = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=False)

    session = relationship("Session", back_populates="medical_fact_revisions")
    reviewer = relationship("User")

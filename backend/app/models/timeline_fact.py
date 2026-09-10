import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import relationship

from app.database import Base


class TimelineFact(Base):
    __tablename__ = "timeline_fact"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Existing generic timeline scaffold; no supported producer or API yet.
    source_type = Column(String, nullable=False)
    source_id = Column(String, nullable=True)
    source_field = Column(String, nullable=True)
    fact_type = Column(String, nullable=False)
    fact_data = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=True)
    timestamp_precision = Column(String, nullable=True)
    is_approximate = Column(Integer, nullable=False, server_default="0")
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
    session = relationship("Session", back_populates="timeline_facts")

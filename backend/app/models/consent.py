import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, UniqueConstraint, text

from app.database import Base


class Consent(Base):
    __tablename__ = "consents"
    __table_args__ = (UniqueConstraint("session_id", name="uq_consents_session"),)

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    voice_processing = Column(Boolean, nullable=False)
    document_processing = Column(Boolean, nullable=False)
    share_with_doctor = Column(Boolean, nullable=False)
    recorded_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    # optional consent version field can be added later
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime(timezone=True), onupdate=text("CURRENT_TIMESTAMP"))

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, text

from app.database import Base


class ABDMRecord(Base):
    __tablename__ = "abdm_records"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    patient_id = Column(
        String,
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    abha_number = Column(String(32), nullable=True)
    abha_address = Column(String(128), nullable=True)
    abha_status = Column(String(32), default="unverified", nullable=False, index=True)
    care_context_reference = Column(String(128), nullable=True)
    care_context_display = Column(String(256), nullable=True)
    care_context_status = Column(String(32), default="unlinked", nullable=False, index=True)
    care_context_linked_at = Column(DateTime(timezone=True), nullable=True)
    his_dispatch_status = Column(String(32), default="not_dispatched", nullable=False, index=True)
    his_dispatch_receipt = Column(Text, nullable=True)
    his_dispatched_at = Column(DateTime(timezone=True), nullable=True)
    consent_artefact_id = Column(String(128), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    updated_at = Column(DateTime(timezone=True), onupdate=text("CURRENT_TIMESTAMP"))

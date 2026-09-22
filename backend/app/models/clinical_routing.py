import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, text

from app.database import Base


class RapidRoutingRun(Base):
    __tablename__ = "rapid_routing_runs"

    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True)
    patient_id = Column(
        String, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    complaint_input_json = Column(JSON, nullable=True)
    chief_complaint = Column(String(64), nullable=True, index=True)
    complaint_confirmed_at = Column(DateTime(timezone=True), nullable=True)
    protocol_version = Column(String(32), nullable=False, default="1.0.0")
    revision = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(DateTime(timezone=True), nullable=True)


class ClinicalRoutingResult(Base):
    __tablename__ = "clinical_routing_results"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    patient_id = Column(
        String, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chief_complaint = Column(String(64), nullable=False)
    routing_state = Column(String(40), nullable=False, index=True)
    suggested_specialty = Column(String(64), nullable=False)
    protocol_version = Column(String(32), nullable=False)
    supporting_evidence_ids_json = Column(JSON, nullable=False, default=list)
    triggered_rule_ids_json = Column(JSON, nullable=False, default=list)
    questions_asked_json = Column(JSON, nullable=False, default=list)
    questions_skipped_json = Column(JSON, nullable=False, default=list)
    completed_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(DateTime(timezone=True), nullable=True)

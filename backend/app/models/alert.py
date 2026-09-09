import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, UniqueConstraint, text

from app.database import Base


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("session_id", "rule_id", name="uq_session_rule_alert"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    rule_id = Column(String, nullable=False, index=True)
    rule_version = Column(String, nullable=False)
    priority = Column(String, nullable=False)
    category = Column(String, nullable=False)
    reason = Column(String, nullable=False)
    triggering_facts_json = Column(JSON, nullable=False)
    status = Column(String, nullable=False, default="new", index=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String, nullable=True)
    acknowledgement_note = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), index=True
    )
    updated_at = Column(DateTime(timezone=True), nullable=True)

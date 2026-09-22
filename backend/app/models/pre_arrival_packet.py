import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, UniqueConstraint, text

from app.database import Base


class PreArrivalPacketRecord(Base):
    __tablename__ = "pre_arrival_packets"
    __table_args__ = (
        UniqueConstraint("session_id", "packet_version", name="uq_pre_arrival_packet_version"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False, index=True)
    hospital_id = Column(String, ForeignKey("hospitals.id"), nullable=False, index=True)
    doctor_id = Column(
        String, ForeignKey("doctor_profiles.doctor_user_id"), nullable=False, index=True
    )
    packet_version = Column(String(16), nullable=False, default="1.0")
    snapshot_json = Column(JSON, nullable=False)
    status = Column(String(16), nullable=False, default="ACTIVE")
    handoff_token_hash = Column(String(64), unique=True, nullable=True, index=True)
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    handoff_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)

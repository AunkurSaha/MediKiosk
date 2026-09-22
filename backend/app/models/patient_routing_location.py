import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, text

from app.database import Base


class PatientRoutingLocation(Base):
    __tablename__ = "patient_routing_locations"
    __table_args__ = (UniqueConstraint("session_id", name="uq_patient_routing_location_session"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id = Column(
        String, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source = Column(String(32), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    locality = Column(String(120), nullable=True)
    postal_code = Column(String(20), nullable=True)
    precision = Column(String(32), nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    captured_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

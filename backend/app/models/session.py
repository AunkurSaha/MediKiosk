import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, text
from sqlalchemy.orm import relationship

from app.database import Base


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    hospital_id = Column(String, ForeignKey("hospitals.id", ondelete="SET NULL"), nullable=True, index=True)
    selected_doctor_id = Column(String, ForeignKey("doctor_profiles.doctor_user_id", ondelete="SET NULL"), nullable=True, index=True)
    hospital_token = Column(String, nullable=False)
    language = Column(String, nullable=False)  # e.g., 'en', 'bn', 'hi'
    status = Column(
        String, nullable=False
    )  # intake, ready_for_review, under_review, confirmed, cancelled
    started_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime(timezone=True), onupdate=text("CURRENT_TIMESTAMP"))

    # Relationships to extracted facts
    medication_facts = relationship("MedicationFact", back_populates="session")
    lab_facts = relationship("LabFact", back_populates="session")
    timeline_facts = relationship("TimelineFact", back_populates="session")
    medical_fact_revisions = relationship("MedicalFactRevision", back_populates="session")

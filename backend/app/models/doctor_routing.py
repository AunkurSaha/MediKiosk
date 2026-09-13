import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, UniqueConstraint, text

from app.database import Base


class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"

    doctor_user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    display_name = Column(String(160), nullable=False)
    qualification = Column(String(160), nullable=True)
    active = Column(Boolean, nullable=False, default=True, server_default="1")
    accepting_patients = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class DoctorHospitalMembership(Base):
    __tablename__ = "doctor_hospital_memberships"
    __table_args__ = (UniqueConstraint("doctor_id", "hospital_id", name="uq_doctor_hospital"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    doctor_id = Column(String, ForeignKey("doctor_profiles.doctor_user_id", ondelete="CASCADE"), nullable=False, index=True)
    hospital_id = Column(String, ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True)
    active = Column(Boolean, nullable=False, default=True, server_default="1")


class DoctorSpecialtyMembership(Base):
    __tablename__ = "doctor_specialty_memberships"
    __table_args__ = (UniqueConstraint("doctor_id", "specialty_code", name="uq_doctor_specialty"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    doctor_id = Column(String, ForeignKey("doctor_profiles.doctor_user_id", ondelete="CASCADE"), nullable=False, index=True)
    specialty_code = Column(String(40), nullable=False, index=True)


class DoctorQueueEntry(Base):
    __tablename__ = "doctor_queue_entries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    doctor_id = Column(String, ForeignKey("doctor_profiles.doctor_user_id"), nullable=False, index=True)
    hospital_id = Column(String, ForeignKey("hospitals.id"), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="WAITING", server_default="WAITING", index=True)
    joined_at = Column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    called_at = Column(DateTime(timezone=True), nullable=True)
    consultation_started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

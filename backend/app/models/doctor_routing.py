import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)

from app.database import Base


class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"

    doctor_user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    display_name = Column(String(160), nullable=False)
    qualification = Column(String(160), nullable=True)
    department = Column(String(64), nullable=True)
    primary_specialty = Column(String(64), nullable=True, index=True)
    subspecialties_json = Column(JSON, nullable=False, default=list)
    expertise_tags_json = Column(JSON, nullable=False, default=list)
    years_of_experience = Column(Integer, nullable=False, default=0)
    languages_json = Column(JSON, nullable=False, default=list)
    consultation_types_json = Column(JSON, nullable=False, default=lambda: ["IN_PERSON"])
    availability_status = Column(String(24), nullable=False, default="UNKNOWN")
    availability_revision = Column(Integer, nullable=False, default=1)
    directory_version = Column(String(80), nullable=False, default="demo_doctors_v1")
    is_demo = Column(Boolean, nullable=False, default=False)
    metadata_json = Column("metadata", JSON, nullable=False, default=dict)
    active = Column(Boolean, nullable=False, default=True, server_default="1")
    accepting_patients = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class DoctorHospitalMembership(Base):
    __tablename__ = "doctor_hospital_memberships"
    __table_args__ = (UniqueConstraint("doctor_id", "hospital_id", name="uq_doctor_hospital"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    doctor_id = Column(
        String,
        ForeignKey("doctor_profiles.doctor_user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hospital_id = Column(
        String, ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    active = Column(Boolean, nullable=False, default=True, server_default="1")


class DoctorSpecialtyMembership(Base):
    __tablename__ = "doctor_specialty_memberships"
    __table_args__ = (UniqueConstraint("doctor_id", "specialty_code", name="uq_doctor_specialty"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    doctor_id = Column(
        String,
        ForeignKey("doctor_profiles.doctor_user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    specialty_code = Column(String(40), nullable=False, index=True)


class DoctorQueueEntry(Base):
    __tablename__ = "doctor_queue_entries"
    __table_args__ = (
        UniqueConstraint(
            "hospital_id",
            "doctor_id",
            "service_date",
            "sequence_number",
            name="uq_doctor_daily_queue_sequence",
        ),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    doctor_id = Column(
        String, ForeignKey("doctor_profiles.doctor_user_id"), nullable=False, index=True
    )
    hospital_id = Column(String, ForeignKey("hospitals.id"), nullable=False, index=True)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=True, index=True)
    service_date = Column(Date, nullable=True, index=True)
    sequence_number = Column(Integer, nullable=True)
    visit_token = Column(String(40), nullable=True)
    status = Column(
        String(30), nullable=False, default="WAITING", server_default="WAITING", index=True
    )
    joined_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    called_at = Column(DateTime(timezone=True), nullable=True)
    consultation_started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)


class DoctorMatchResult(Base):
    __tablename__ = "doctor_match_results"
    __table_args__ = (UniqueConstraint("input_signature", name="uq_doctor_match_signature"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id = Column(
        String, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    clinical_routing_result_id = Column(
        String, ForeignKey("clinical_routing_results.id", ondelete="CASCADE"), nullable=False
    )
    mediroute_result_id = Column(
        String, ForeignKey("mediroute_results.id", ondelete="CASCADE"), nullable=True
    )
    facility_id = Column(String, ForeignKey("hospitals.id"), nullable=False, index=True)
    required_specialty = Column(String(64), nullable=False)
    directory_version = Column(String(80), nullable=False)
    protocol_version = Column(String(32), nullable=False)
    input_signature = Column(String(64), nullable=False)
    status = Column(String(48), nullable=False)
    selected_doctor_id = Column(String, ForeignKey("doctor_profiles.doctor_user_id"), nullable=True)
    selected_at = Column(DateTime(timezone=True), nullable=True)
    generated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class DoctorMatchRecommendation(Base):
    __tablename__ = "doctor_match_recommendations"
    __table_args__ = (
        UniqueConstraint("doctor_match_result_id", "doctor_id", name="uq_doctor_match_doctor"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    doctor_match_result_id = Column(
        String,
        ForeignKey("doctor_match_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doctor_id = Column(
        String, ForeignKey("doctor_profiles.doctor_user_id"), nullable=False, index=True
    )
    rank = Column(Integer, nullable=False)
    score = Column(Integer, nullable=False)
    eligibility_reasons_json = Column(JSON, nullable=False, default=list)
    ranking_reasons_json = Column(JSON, nullable=False, default=list)
    score_components_json = Column(JSON, nullable=False, default=dict)
    metadata_json = Column("metadata", JSON, nullable=False, default=dict)

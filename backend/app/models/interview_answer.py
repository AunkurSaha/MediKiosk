import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, text

from app.database import Base


class InterviewAnswer(Base):
    __tablename__ = "interview_answers"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    question_id = Column(String, nullable=False)  # identifier for the question
    field = Column(String, nullable=False)  # e.g., 'chief_complaint', 'onset_duration'
    value_json = Column(Text, nullable=True)  # structured value as JSON string
    raw_value = Column(Text, nullable=True)  # original input from patient
    source = Column(String, nullable=False)  # e.g., 'patient_typed', 'patient_voice'
    language = Column(String, nullable=False)  # language of the answer
    confidence = Column(String, nullable=True)  # optional, for future AI
    verification_status = Column(
        String, nullable=False, default="patient_reported"
    )  # patient_reported, unverified, clinician_verified
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime(timezone=True), onupdate=text("CURRENT_TIMESTAMP"))

import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, UniqueConstraint, text

from app.database import Base


class NormalizationResult(Base):
    __tablename__ = "normalization_results"
    __table_args__ = (UniqueConstraint("source_answer_id", name="uq_normalization_source_answer"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False, index=True)
    source_answer_id = Column(String, ForeignKey("interview_answers.id"), nullable=False)
    provider = Column(String, nullable=False)
    provider_version = Column(String, nullable=False)
    schema_version = Column(String, nullable=False)
    policy_version = Column(String, nullable=False)
    status = Column(String, nullable=False)
    result_json = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

from sqlalchemy import JSON, Column, ForeignKey, Integer, String

from app.database import Base


class InterviewRun(Base):
    __tablename__ = "interview_runs"

    session_id = Column(String, ForeignKey("sessions.id"), primary_key=True)
    flow_id = Column(String, nullable=False)
    flow_version = Column(String, nullable=False)
    flow_snapshot = Column(JSON, nullable=False)
    cursor = Column(String, nullable=True)
    revision = Column(Integer, nullable=False, default=0)


class InterviewRequest(Base):
    """Durable idempotency receipts prevent a delayed retry undoing a later correction."""

    __tablename__ = "interview_requests"

    session_id = Column(String, ForeignKey("interview_runs.session_id"), primary_key=True)
    request_id = Column(String, primary_key=True)
    payload_hash = Column(String, nullable=False)

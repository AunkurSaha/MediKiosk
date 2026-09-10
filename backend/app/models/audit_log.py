import uuid

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_user_id = Column(String, nullable=True)
    actor_type = Column(String, nullable=False)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False, index=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))


class SummaryRevision(Base):
    __tablename__ = "summary_revisions"
    __table_args__ = (
        UniqueConstraint("summary_id", "version", name="uq_summary_revision_version"),
    )
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    summary_id = Column(String, ForeignKey("clinical_summaries.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    revision_type = Column(String, default="edit", nullable=False)
    actor_type = Column(String, default="DOCTOR", nullable=False)
    reviewed_text = Column(Text, nullable=False)
    actor_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    review_notes = Column(Text, nullable=True)
    structured_snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

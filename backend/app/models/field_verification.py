import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import relationship

from app.database import Base


class FieldVerification(Base):
    __tablename__ = "field_verifications"
    __table_args__ = (
        UniqueConstraint("session_id", "field_type", "field_id", name="uq_session_field_verification"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    field_type = Column(String(64), nullable=False, index=True)
    field_id = Column(String(128), nullable=False, index=True)
    status = Column(String(32), default="unverified", nullable=False, index=True)
    verified_by = Column(String, ForeignKey("users.id"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=text("CURRENT_TIMESTAMP"))

    revisions = relationship("FieldVerificationRevision", back_populates="verification", cascade="all, delete-orphan", order_by="FieldVerificationRevision.version.asc()")


class FieldVerificationRevision(Base):
    __tablename__ = "field_verification_revisions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    verification_id = Column(String, ForeignKey("field_verifications.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False)
    actor_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    verification = relationship("FieldVerification", back_populates="revisions")

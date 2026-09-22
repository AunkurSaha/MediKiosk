import uuid

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)

from app.database import Base
from app.domain.clinical_safety import EvidenceSourceType, EvidenceVerificationStatus


class ClinicalEvidence(Base):
    """Append-oriented clinical evidence; never an absolute clinical truth."""

    __tablename__ = "clinical_evidence"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_id",
            "stable_key",
            name="uq_clinical_evidence_provenance",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_clinical_evidence_confidence",
        ),
        CheckConstraint(
            "source_type IN (" + ",".join(f"'{item.value}'" for item in EvidenceSourceType) + ")",
            name="ck_clinical_evidence_source_type",
        ),
        CheckConstraint(
            "verification_status IN ("
            + ",".join(f"'{item.value}'" for item in EvidenceVerificationStatus)
            + ")",
            name="ck_clinical_evidence_verification_status",
        ),
        Index("ix_clinical_evidence_patient_created", "patient_id", "created_at"),
        Index("ix_clinical_evidence_session_concept", "session_id", "concept_code"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_id = Column(
        String, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id = Column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    concept_code = Column(String(160), nullable=True, index=True)
    value_json = Column(JSON, nullable=True)
    source_type = Column(String(40), nullable=False, index=True)
    source_id = Column(String, nullable=False)
    stable_key = Column(String(160), nullable=False, server_default="value")
    original_text = Column(Text, nullable=True)
    normalized_text = Column(Text, nullable=True)
    translated_text = Column(Text, nullable=True)
    language = Column(String(16), nullable=True)
    confidence = Column(Float, nullable=True)
    verification_status = Column(String(40), nullable=False, index=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    verified_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verification_reason = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        index=True,
    )
    updated_at = Column(DateTime(timezone=True), nullable=True)


class ClinicalEvidenceConflict(Base):
    __tablename__ = "clinical_evidence_conflicts"
    __table_args__ = (
        UniqueConstraint(
            "evidence_a_id", "evidence_b_id", name="uq_clinical_evidence_conflict_pair"
        ),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    evidence_a_id = Column(
        String, ForeignKey("clinical_evidence.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_b_id = Column(
        String, ForeignKey("clinical_evidence.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason = Column(Text, nullable=False)
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

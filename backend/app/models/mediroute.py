import uuid

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

from app.database import Base


class MediRouteResult(Base):
    __tablename__ = "mediroute_results"
    __table_args__ = (UniqueConstraint("input_signature", name="uq_mediroute_input_signature"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id = Column(
        String, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    clinical_routing_result_id = Column(
        String,
        ForeignKey("clinical_routing_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    location_id = Column(
        String, ForeignKey("patient_routing_locations.id", ondelete="SET NULL"), nullable=True
    )
    routing_state = Column(String(40), nullable=False)
    suggested_specialty = Column(String(64), nullable=False)
    directory_version = Column(String(80), nullable=False)
    protocol_version = Column(String(32), nullable=False)
    input_signature = Column(String(64), nullable=False)
    required_specialty = Column(String(64), nullable=False)
    required_capabilities_json = Column(JSON, nullable=False, default=list)
    preferred_capabilities_json = Column(JSON, nullable=False, default=list)
    status = Column(String(32), nullable=False)
    generated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    recommendations = relationship(
        "MediRouteRecommendation", back_populates="result", cascade="all, delete-orphan"
    )


class MediRouteRecommendation(Base):
    __tablename__ = "mediroute_recommendations"
    __table_args__ = (
        UniqueConstraint("mediroute_result_id", "facility_id", name="uq_mediroute_result_facility"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    mediroute_result_id = Column(
        String, ForeignKey("mediroute_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id = Column(String, ForeignKey("hospitals.id"), nullable=False, index=True)
    rank = Column(Integer, nullable=False)
    distance_km = Column(Float, nullable=True)
    score = Column(Float, nullable=False)
    eligibility_reasons_json = Column(JSON, nullable=False, default=list)
    ranking_reasons_json = Column(JSON, nullable=False, default=list)
    details_json = Column("metadata", JSON, nullable=False, default=dict)
    result = relationship("MediRouteResult", back_populates="recommendations")
    facility = relationship("Hospital")

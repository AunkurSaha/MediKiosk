import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, Float, Integer, String, text

from app.database import Base


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        CheckConstraint(
            "gender IS NULL OR gender IN ('female', 'male', 'non_binary', 'other', 'prefer_not_to_say')",
            name="ck_patients_gender",
        ),
        CheckConstraint(
            "age_years IS NULL OR age_years BETWEEN 0 AND 120", name="ck_patients_age_years"
        ),
        CheckConstraint(
            "height_cm IS NULL OR height_cm BETWEEN 30 AND 250", name="ck_patients_height_cm"
        ),
        CheckConstraint(
            "weight_kg IS NULL OR weight_kg BETWEEN 1 AND 500", name="ck_patients_weight_kg"
        ),
    )

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    gender = Column(String(32), nullable=True)
    age_years = Column(Integer, nullable=True)
    height_cm = Column(Float, nullable=True)
    weight_kg = Column(Float, nullable=True)
    demo_abha_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime(timezone=True), onupdate=text("CURRENT_TIMESTAMP"))

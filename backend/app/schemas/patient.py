from typing import Literal

from pydantic import Field

from .common import APIModel, UTCDate


class PatientCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    gender: Literal["female", "male", "non_binary", "other", "prefer_not_to_say"] | None = None
    age_years: int | None = Field(default=None, ge=0, le=120)
    height_cm: float | None = Field(default=None, ge=30, le=250)
    weight_kg: float | None = Field(default=None, ge=1, le=500)
    demo_abha_id: str | None = Field(default=None, max_length=80)


class Patient(PatientCreate):
    id: str
    created_at: UTCDate
    updated_at: UTCDate | None = None
